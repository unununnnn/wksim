# 冻结五切片最终提交序列集成审计

2026-09-14。只读五组冻结候选与历史回执。主仓 git index / refs 只读。新写仅
`validation/coordination/cursor-five-slice-final-integration2-20260914-01/**`。
在隔离临时仓用 `hash-object --no-filters` + `commit-tree` 模拟 A→B→C→D→E 与
E→D→C→B→A，并在每步及最终 empty commit 后核祖先语义与各切片代表测试。
Windows 3.13.11 与 Ubuntu-22.04 / 3.10.12 均覆盖。未重跑 budget 153、G3 179。

**总裁决：PASS（0 P1 / 0 P2 / 6 P3）。** 候选哈希 18/18 命中钉值。两序终态 tree
均为 `317b98b873ba8c2e62a478144107a795929fa4b5`，与顺序无关，且跨主机逐步
commit/tree 相同。提交后 `6eafdf9` 与 `f333316e` 仍为祖先，当前 HEAD 不等于来源钉。
related 不含 frame 路径；frame 进入 disposable HEAD 后 budget 30 仍绿。Full/frame
双顺序均绿。empty commit 树不变、HEAD 前进，HEAD 依赖代表项仍过。

这不是 owner 批准，也不关闭 #39 / #59 / #102 / G1 / G3 / G5 / G6 / Full。不是一次主仓 commit。

## 派发

```text
工作类别：只读五切片最终提交序列集成审计
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、CONTEXT.md、
      五组候选与既有 G1/G5 finalize2、G3 precommit、budget P2、
      frame precommit、Full precommit、Full×frame 双序回执
module / interface：只读评估
                   A G1/G5 离线身份门（SOURCE_HEAD 祖先钉 + 四枚既有离线依赖）
                   B G3 exact-clearance
                   C E0 budget 台账 / related 来源钉
                   D G6 frame/datum
                   E Full 原始 AC 缺口账本
独占写入：validation/coordination/cursor-five-slice-final-integration2-20260914-01/**
依赖（只读）：上列十八份候选；四枚 G1/G5 force-add；三条 related 未跟踪前沿；
             HEAD 七行产品源、G3 planning/bspline、budget/frame pins、
             Full cited_sources 中已在 HEAD 的文件
验证：独立重算候选哈希；AST 扫描 exact-HEAD 等式；依赖闭包与路径不相交；
      隔离仓 A→B→C→D→E 与 E→D→C→B→A；每步祖先 / git show HEAD blob；
      Windows / Ubuntu-22.04 代表测试；empty commit；related×frame 交叉；
      Full/frame 双顺序
范围外：改候选或历史回执；主仓 add/commit/stage/reset/clean；
        整仓 archive 进内存；budget 153 / G3 179 / 53 / 721 /
        frame 45 / Full 81 / #83；
        native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行
```

本界面不可选 `gpt-5.6-luna` / `gpt-6-astra`。审计在主代理完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 主仓 HEAD 仍为 `6eafdf9`，`f333316e` 为祖先 | **PASS** | 开工与收工均为 `6eafdf9c…`，祖先退出码 0；index SHA-256 仍 `de15d624…` / 1555140；`diff --cached` 空 |
| 十八份候选哈希 = 派发钉 | **PASS** | 独立重算 18/18；见 `candidate-hashes.json` |
| 四枚 G1/G5 既有离线依赖未漂 | **PASS** | 两枚飞行钉 + 两个 helper 哈希与 finalize2 / repair 钉一致 |
| 路径 / 切片所有权不相交 | **PASS** | A∩B∩C∩D∩E 拥有路径空 |
| 无当前 HEAD 精确相等缺陷 | **PASS** | 无 `PINNED_HEAD =`；无 `assertEqual(identities["head"], SOURCE_HEAD)`；Full JSON `head` 是捕获钉；budget/frame 用祖先 |
| related 不含 frame，不对照当前 HEAD | **PASS** | 三条 B1/B4 前沿；`tracked_at_source_head=false`；无 `tracked_at_head`；无 `33c490…` |
| 低内存隔离仓 | **PASS** | alternates + `commit-tree`；选择性 `checkout-index`（约 255 / 10388）；无整仓 archive |
| 每步旧基线仍是祖先 | **PASS** | 两主机 × 两序 × 六步：`6eafdf9` 与 `f333316e` 祖先退出码均为 0；`head_equals_source=false` |
| 每步已提交切片 `git show HEAD` blob | **PASS** | SHA-256 等于候选钉；未提交切片不在 HEAD |
| 最终 tree 与顺序无关 | **PASS** | ABCDE 与 EDCBA 终态 tree 均为 `317b98b8…` |
| 跨主机逐步身份 | **PASS** | Windows 与 Ubuntu-22.04 十二步 commit/tree 全部相同 |
| empty commit 树不变 | **PASS** | ABCDE empty `1069dbf0…`、EDCBA empty `13a691fc…`，tree 仍 `317b98b8…` |
| 代表测试在 HEAD 前进后仍绿 | **PASS** | 见下表；G3 4、budget 30、frame 12、G1/G5 4、Full 5/2 |
| related×frame 交叉 | **PASS** | frame 已跟踪后 budget 30 两端仍 OK；related 未入库 |
| Full/frame 双顺序 | **PASS** | ABCDE 含 D→E；EDCBA 含 E→D；两端均绿 |
| 主仓未被 add/commit/stage/reset/clean | **PASS** | HEAD / refs/heads/main / index 内容钉未动 |
| 本审查总体 | **PASS** | 0 P1 / 0 P2 / 6 P3。不关闭任何 issue / gate |

## 冻结候选（开工 = 收工）

| 切片 | 路径 | 字节 | SHA-256 | add |
| --- | --- | ---: | --- | --- |
| A | `validation/test_g1_g5_offline_drift.py` | 42074 | `83234a89…a12c5` | 普通 |
| A | `…/independent-candidate/flight-audit.json` | 7005 | `b1df8a36…eb68b9a` | **`-f`** |
| A | `…/flown-source/manifest.json` | 12309 | `156ed0de…3e1719` | **`-f`** |
| A | `…/stdlib_identity_plugin.py` | 3373 | `e7044fb5…20101f` | **`-f`** |
| A | `…/isolation_after_g1g5.py` | 2067 | `e540760a…33fa94` | **`-f`** |
| B | `Simulator/wksim_planning/ego_exact_clearance.py` | 38854 | `8b1d2dd8…fd46ea` | 普通 |
| B | `validation/test_ego_exact_clearance.py` | 56737 | `d3541280…62ae17` | 普通 |
| B | `docs/plan/102-exact-clearance-candidate.md` | 17982 | `b1203d51…41b0fe` | 普通 |
| C | `docs/plan/59-e0-budget-approval-provenance-20260914.md` | 21203 | `15b4f457…d277bd` | 普通 |
| C | `validation/e0-budget-approval-provenance-20260914.json` | 285820 | `2962931a…544d3d` | 普通 |
| C | `validation/test_e0_budget_approval_provenance.py` | 151778 | `6030470a…636b44` | 普通 |
| D | `docs/plan/59-e0-frame-datum-binding-20260914.md` | 15449 | `3fbb0e7f…b553f8` | 普通 |
| D | `validation/e0-frame-datum-binding-20260914.json` | 105018 | `5d589075…45b69f` | 普通 |
| D | `validation/test_e0_frame_datum_binding.py` | 77146 | `e412f2d1…910da6` | 普通 |
| E | `docs/plan/full-original-ac-gap-ledger-20260914.md` | 25570 | `5a4d9a64…4ad3e` | 普通 |
| E | `validation/full-original-ac-gap-ledger-20260914.json` | 225429 | `4e1f9b9e…fd1d16` | 普通 |
| E | `validation/full-original-ac-gap-ledger-snapshot-20260914.json` | 91924 | `c8af0dce…ae1ef4` | 普通 |
| E | `validation/test_full_original_ac_gap_ledger.py` | 75771 | `d2a241c9…367a1` | 普通 |

三条 related 前沿文件只作未跟踪叠入，不进入任一切片 commit。哈希见 `candidate-hashes.json`。

## 代表集与复用的全量证据

本审计现场跑代表集，不重跑大套件：

| 切片 | 本审计代表 | 复用的冻结全量 |
| --- | --- | --- |
| A | HeadIdentity + GuardScope + IndependentEvidence + Telemetry（4） | G1/G5 finalize2 / repair：Windows 31 passed + 2 skipped；Ubuntu 33 |
| B | 公差 / 未接线 / 结构 fail-closed / 词表（4） | G3 precommit 53/53；postrepair3 721 只核哈希 |
| C | 官方 budget 30 | P2 repair Windows 153 OK；本审计不重跑 153 |
| D | frame 12 | frame precommit / p2-finalize 45；本审计不重跑 45 |
| E | 身份 / fail-closed / 总量 / mutation（5；empty 后 2） | Full precommit 与 Full×frame 81/81；本审计不重跑 81 |

isolation 节点必须 `pytest -p stdlib_identity_plugin`，不是 unittest 可替代的 HEAD 祖先项。Full `test_cited_sources_exist` 依赖目录级 cited sources，已由冻结 81 覆盖，本代表集不重走该存在性遍历。

## 两序列（逐步 HEAD / tree）

作者/提交日期固定。Windows 与 Ubuntu-22.04 逐步 SHA 相同。全文见 `sequence-matrix.json`。

| 序列 | 步 | HEAD | tree |
| --- | --- | --- | --- |
| A→B→C→D→E | after A | `0734d429db8c…` | `ed8281dc3836…` |
| A→B→C→D→E | after B | `68a36397576b…` | `0b500bca489d…` |
| A→B→C→D→E | after C | `7ca441436a0b…` | `58f850956ca4…` |
| A→B→C→D→E | after D | `bac7ddf7c1aa…` | `a141ebf59b88…` |
| A→B→C→D→E | after E | `ad6b3a79421c…` | `317b98b873ba…` |
| A→B→C→D→E | empty | `1069dbf0a7c2…` | `317b98b873ba…` |
| E→D→C→B→A | after E | `46156d96e871…` | `6204cc1243f1…` |
| E→D→C→B→A | after D | `b53ef69ccf56…` | `e608b71d37c9…` |
| E→D→C→B→A | after C | `0abebf1bb93e…` | `3dcfaa736b71…` |
| E→D→C→B→A | after B | `65e2146e62bc…` | `41102612a7be…` |
| E→D→C→B→A | after A | `91748fbf94a3…` | `317b98b873ba…` |
| E→D→C→B→A | empty | `13a691fc8791…` | `317b98b873ba…` |

after-A tree `ed8281dc…` 与既有 G1/G5 repair ABC after-A tree 相同，说明未改 A 四依赖叠法之外的基线。EDCBA after-D tree `e608b71d…` 与既有 Full×frame Windows Frame→Full 终态 tree 相同，说明未改 D+E 普通 add 集合。

## 本审查亲自执行的运行

| 平台 | 序列/步 | G1/G5 | G3 | budget | frame | Full |
| --- | --- | --- | --- | --- | --- | --- |
| Windows 3.13.11 | ABCDE after A | 4 OK | — | — | — | — |
| Windows 3.13.11 | ABCDE after B | 4 OK | 4 OK | — | — | — |
| Windows 3.13.11 | ABCDE after C | 4 OK | 4 OK | 30 OK / 10.05 s | — | — |
| Windows 3.13.11 | ABCDE after D | 4 OK | 4 OK | 30 OK | 12 OK / 51.85 s | — |
| Windows 3.13.11 | ABCDE after E | 4 OK | 4 OK | 30 OK | 12 OK | 5 OK |
| Windows 3.13.11 | ABCDE empty | 1 OK | 4 OK | 2 OK | 2 OK | 2 OK |
| Windows 3.13.11 | EDCBA after E | — | — | — | — | 5 OK |
| Windows 3.13.11 | EDCBA after D | — | — | — | 12 OK / 53.33 s | 5 OK |
| Windows 3.13.11 | EDCBA after C | — | — | 30 OK | 12 OK | 5 OK |
| Windows 3.13.11 | EDCBA after A / empty | 4 / 1 OK | 4 OK | 30 / 2 OK | 12 / 2 OK | 5 / 2 OK |
| Ubuntu 3.10.12 | ABCDE after C | 4 OK | 4 OK | 30 OK / 7.69 s | — | — |
| Ubuntu 3.10.12 | ABCDE after D | 4 OK | 4 OK | 30 OK | 12 OK / 22.72 s | — |
| Ubuntu 3.10.12 | ABCDE after E / empty | 4 / 1 OK | 4 OK | 30 / 2 OK | 12 / 2 OK | 5 / 2 OK |
| Ubuntu 3.10.12 | EDCBA after D | — | — | — | 12 OK / 24.15 s | 5 OK |
| Ubuntu 3.10.12 | EDCBA after C | — | — | 30 OK / 8.52 s | 12 OK | 5 OK |
| Ubuntu 3.10.12 | EDCBA after A / empty | 4 / 1 OK | 4 OK | 30 / 2 OK | 12 / 2 OK | 5 / 2 OK |

每步 `head_equals_source=false`，`source_ancestor_exit=0`，`f333316_ancestor_exit=0`。empty 后 tree 未变。

首轮 Windows 把 isolation 节点放进 unittest，该节点要求 `pytest -p`，按设计红。首轮 Full `test_cited_sources_exist` 因目录 `validation/pid-final-px4-20260909` 未按前缀检出而红。夹具修正后现场代表集绿。这两类不是候选缺陷。

## exact-HEAD 与交叉语义

- G1/G5：`SOURCE_HEAD` 只作 `merge-base --is-ancestor`；L540 是 `assertNotEqual(identities["head"], SOURCE_HEAD)`。L414 只钉常量本身。
- Budget：`observed_at.head` 等于来源钉；`test_source_head_is_ancestor_pin_not_current_equality` 在 FrozenInputTests（30 代表集内）。
- Frame：`test_head_and_baseline` 查祖先，不要求精确 HEAD。
- Full：账本 / 快照 JSON 的 `head` 是捕获钉，套件不调用 `rev-parse HEAD`。
- G3：无 git HEAD 身份。
- related 三条是 B1/B4 前沿，不是当前 frame 候选。frame 进入 disposable HEAD 后，budget 30 仍过，related 未升 pin / owner / derivation。

## 发现（P1–P3）

| id | 级 | 标题 |
| --- | --- | --- |
| — | P1 | **无** |
| — | P2 | **无** |
| P3-ISOLATION-NEEDS-PYTEST-PLUGIN | P3 | isolation 节点必须 `-p stdlib_identity_plugin`。本审计代表集用 unittest 4 项覆盖 HEAD 祖先。冻结 repair 9/9 不重跑。 |
| P3-FULL-CITED-DIR-CHECKOUT | P3 | 首轮文件级 checkout 漏了 cited 目录。代表集改为身份 / fail-closed；81 存在性遍历复用冻结回执。 |
| P3-LARGE-SUITES-REUSED | P3 | 按派发不重跑 153 / 179 / 53 / 721 / 45 / 81 / #83。 |
| P3-G1G5-INHERITED-FORCEADD | P3 | 切片 A 仍要 `git add -f` 四枚被 `/validation/*/` 忽略的离线依赖。 |
| P3-G1G5-CRLF-PIN | P3 | G1/G5 套件与 helper 钉含 CR（917 / 100 / 54）。临时仓用 `--no-filters`。 |
| P3-UNRELATED-DIRTY | P3 | 事先已有的两处已跟踪改动未触碰，不得纳入真实提交。 |

## 非声称

不关闭 #39 / #59 / #102 / G1 / G3 / G5 / G6 / Full，不批准 owner 项，不改判 R1 `numerical_failed`，不把 7/7 部分离线写成整行覆盖，也不把代表 4/30/12/5 写成 53/53、153、179、721、45、81 或飞行验收。未做 native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83。主仓无 `git add` / commit / stage / reset / clean。可弃用仓里的 commit 只用于提交后探针，不是项目提交。本文件不是 commit。
