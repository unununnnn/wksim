# G3 exact-clearance 预提交 / 干净检出审计

2026-09-14。只读审计未入库、未接线的终稿候选。**未改候选。** 本审查写入仅在
`validation/coordination/cursor-g3-exact-precommit-audit-20260914-01/**`。

**裁决：PASS。** 无 P1 / P2。三则 P3（证据目录需 force-add；合同引用其他被忽略回执；工作树两处无关已跟踪脏文件不得纳入）。

`git archive HEAD`（10370 文件）再只叠三份候选后，Windows 与 Ubuntu-22.04 聚焦套件均为 53/53 pytest、53 unittest。未发现缺失的被忽略/未跟踪运行时或测试依赖。179 四文件套件因先验捕获与源哈希仍匹配而跳过。

这不是晋升，不关闭 #102 / #39 / G3 / Full，也不是一次实际 commit。

## 派发

```text
工作类别：只读预提交 / 干净检出审计
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、102-exact-clearance-candidate.md、
      候选源码与测试、postrepair3 全量复审、docfix2 finalize
module / interface：只读评估终稿候选
                   Simulator/wksim_planning/ego_exact_clearance.py
                   validation/test_ego_exact_clearance.py
                   docs/plan/102-exact-clearance-candidate.md
独占写入：validation/coordination/cursor-g3-exact-precommit-audit-20260914-01/**
依赖（只读）：HEAD 中的 evaluator / admission / binding / payload，
             以及上述两份终审回执
验证：git archive HEAD + 仅三份候选的一次性干净树；
      Windows / Ubuntu-22.04 聚焦 pytest+unittest；
      先验 179 捕获与四文件/封印哈希对照
范围外：改候选、commit/stage/reset/clean、git worktree、
        native / model / MATLAB / ROS / DDS / SITL / FC / UE /
        build / flight / #83、hostile 721、四文件 179 重跑
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审查在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 候选哈希 = 钉扎终稿 | **PASS** | `8b1d2dd8…` / `d3541280…` / `b1203d51…`，开工与收工一致 |
| 封印未变 | **PASS** | admission `f88fa9c6…`，pump `c9b541b4…` |
| 干净树 = archive HEAD + 仅三份候选 | **PASS** | 未用 worktree；干净树无 `.git`；叠入前三份候选不存在 |
| 聚焦套件可在干净树运行 | **PASS** | 两端 53/53 pytest、53 unittest |
| 无缺失的忽略/未跟踪运行时或测试依赖 | **PASS** | `bspline.json` 已在 HEAD；其余依赖已在 archive |
| 179 可跳过 | **PASS** | 四文件配套 worktree=HEAD；先验捕获 SHA 仍匹配 SHA256SUMS |
| 最小 add 集正确 | **PASS** | 普通 add 三份；测试所需 force-add 为空 |
| 本审查总体 | **PASS** | 无 P1 / P2 |

## 身份与冻结哈希

开工冻结并在全部运行后回检，字节未变：

| 路径 | 字节 | SHA-256 |
| --- | ---: | --- |
| `Simulator/wksim_planning/ego_exact_clearance.py` | 38854 | `8b1d2dd8c097447d32d5d4f22b5827f8712ac84c9de0e963983d24e73efd46ea` |
| `validation/test_ego_exact_clearance.py` | 56737 | `d3541280c8d03127b047a2c7d67ce5581b6ff0c4dd0378b96209550ff762ae17` |
| `docs/plan/102-exact-clearance-candidate.md` | 17982 | `b1203d51676cb7ac8676e0f33c7769da2a599f93b2e57560b073f930fc41b0fe` |
| `Simulator/wksim_planning/ego_scene_admission.py` | 34774 | `f88fa9c67b0410b8d7e65145008b21173959c03b6f0773c841cdb5e7e3ff7eca` |
| `Simulator/wksim_runtime/planner_transport_pump.py` | 32032 | `c9b541b4fb6112b09aacdb405838aa2f3c8935e144a21067f9c420f473279d27` |
| `validation/ego-planner-static-20260912-02/bspline.json` | 4452 | `d4d318cc99cc55460a5de229881f8c83bbd032a7c97fd80f7f603ca4e2684447` |

终稿合同是 `b1203d51…`，不是 postrepair3 当时的 `7b1e9bfa…`，也不是第一次文档修补的错误 R2 `a6637ed8…`。HEAD 仍为 `6eafdf9c0b734db07a9fe790c86b409d3468c10b`。无 commit / stage / reset / clean。工作树上原先已有的两处已跟踪改动未触碰。

## 干净树

方法：`git archive --format=tar HEAD` 写到 `%TEMP%/wksim-g3-exact-precommit-20260914/HEAD.tar`（5,971,220,480 字节），再分别解到 Windows 与 `/tmp` Ubuntu 树，然后只复制三份候选。未使用 `git worktree`，未改仓库元数据，干净树内无 `.git`。

| 检查 | Windows | Ubuntu-22.04 |
| --- | --- | --- |
| 解出文件数 | 10370 | 10370 |
| 叠入前三份候选存在 | 否 | 否 |
| 叠入前 `bspline.json` | 是，`d4d318cc…` | 是 |
| 叠入后候选哈希 | 与钉扎一致 | 与钉扎一致 |

测试从干净树根目录运行，`PYTHONPATH` 指向该树，`PYTHONDONTWRITEBYTECODE=1`。捕获只写本审查目录。

## 本审查亲自执行的运行

| 平台 | 命令 | 结果 |
| --- | --- | --- |
| Windows，Python 3.13.11 | `python -B -m pytest validation/test_ego_exact_clearance.py -q` | **53 passed, 162 subtests** |
| Windows | `python -B -m unittest validation.test_ego_exact_clearance` | **53 tests OK** |
| Ubuntu 22.04.5 LTS，Python 3.10.12 | `python3 -B -m pytest validation/test_ego_exact_clearance.py -q` | **53 passed, 162 subtests** |
| Ubuntu-22.04 | `python3 -B -m unittest validation.test_ego_exact_clearance` | **53 tests OK** |

未重跑 hostile 721、四文件 179 或 #83。

## 179 跳过依据

`cursor-g3-exact-postrepair3-review-20260914-01` 在同一 Python/测试哈希上记录两端 **179 passed, 216 subtests**。本审查核验：

* 四文件配套 `test_ego_scene_admission.py` / `test_planner_transport_pump.py` / `test_planner_transport_receiver.py` 的 worktree SHA-1 等于 HEAD blob；
* 封印与候选 Python/测试哈希相对 postrepair3 未变；
* 先验捕获 `pytest-four-file-windows.txt` = `edfe0667…`，`pytest-four-file-linux-ubuntu-22.04.txt` = `7b79d411…`，仍等于该包 SHA256SUMS；
* 唯一变化是合同 `7b1e9bfa…` → `b1203d51…`，四文件套件不读该文档。

因此 179 不必重跑。docfix2 finalize 已关闭当时的两则文档 P3；代码侧 P3-N1（n-partition 门不是公开可演示裁决）仍在，不属于本预提交缺口。

## 最小 add 集

聚焦套件在干净检出上的最小集合是 **三份普通 `git add`**。测试所需 **force-add 为空**。

`bspline.json` 受 `/validation/*/` 规则约束，但它已经在 HEAD 中，archive 含该文件。新的未跟踪 `validation/` 子目录文件才需要 `-f`。

若要把终审证据一并入库，才需要对选中的 durable 审查产物 `git add -f`：postrepair3 的 review/SHA256SUMS/四文件与候选捕获、docfix2 finalize 的 review/SHA256SUMS、以及本审计目录。它们都被 `/validation/*/` 忽略。详见 `minimal-commit-manifest.txt`。

不要纳入：`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`（已跟踪但无关脏文件）、第一次文档修补（错误 R2，不可信）、其他未跟踪脏文件。

## 发现（P1–P3）

| id | 级 | 标题 |
| --- | --- | --- |
| — | P1 | **无** |
| — | P2 | **无** |
| P3-EVIDENCE-FORCEADD | P3 | 选中的 durable 审查目录被 `/validation/*/` 忽略；要随候选入库必须 `git add -f`。不影响干净树跑通聚焦套件。 |
| P3-DOC-IGNORED-CITES | P3 | 终稿合同仍引用 `deepseek-g3-exact-clearance-20260914-01` 与早期 repair 回执；那些路径同样被忽略，不在最小测试 add 集中。 |
| P3-UNRELATED-DIRTY | P3 | 工作树已有两处已跟踪改动，与本候选无关，不得纳入本次提交。 |

无发现构成干净检出无法运行，或隐藏的未跟踪测试依赖。

## 非声称

不关闭 #102 / #39 / G3 / Full，不批准把该谓词升为默认严格门。无动力学、跟踪误差、控制器滞后、力、冲量、地形、规划器、套接字、发布或飞行安全声称。未做 native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83。无 Git 或 GitHub 变更。本文件不是 commit。
