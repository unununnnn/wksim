# G3 exact-clearance 文档 delta 终审（docfix2 finalize）

2026-09-14。独立终审未入库、未接线的最终候选合同。**未改候选。** 本审查写入仅在
`validation/coordination/cursor-g3-exact-docfix2-finalize-20260914-01/**`。

**裁决：PASS。** 无 P1 / P2 / P3。

终稿合同哈希为 `b1203d51…`。先验 delta 在 Windows 与 Ubuntu-22.04 均为 55/55 PASS；其嵌入哈希与当前终稿一致。独立快速语义抽查 107/107 PASS。未重跑长测试、hostile 721、候选 pytest/unittest、四文件套件或 #83。

这不是晋升，不关闭 #102 / #39 / G3 / Full。

## 派发

```text
工作类别：独立文档 delta 终审（非新架构验收、非历史对照、非晋升）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、102-exact-clearance-candidate.md、
      候选源码决策路径、delta 包、postrepair3 PASS 包
module / interface：只读评估 docs/plan/102-exact-clearance-candidate.md
                   与 ego_exact_clearance 决策极性（不改候选）
独占写入：validation/coordination/cursor-g3-exact-docfix2-finalize-20260914-01/**
依赖（只读）：
  docs/plan/102-exact-clearance-candidate.md
  Simulator/wksim_planning/ego_exact_clearance.py
  validation/test_ego_exact_clearance.py
  validation/coordination/cursor-g3-exact-docfix2-delta-review-20260914-01/**
  validation/coordination/cursor-g3-exact-postrepair3-review-20260914-01/**
验证：独立重算当前哈希；先验 delta JSON/captures 内部一致性；
      嵌入哈希对应当前终稿 b1203d51…；快速本地语义抽查
范围外：native / model / MATLAB / ROS / DDS / SITL / FC / UE /
        build / flight / #83、长测试、hostile 721、pytest 53、
        四文件套件、alternating_witness 60200 路径、晋升、Git 变更
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审查在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 身份与当前哈希

独立重算，与 delta 冻结、delta 两端结果 JSON 嵌入值一致：

| 路径 | 字节 | SHA-256 |
| --- | ---: | --- |
| `docs/plan/102-exact-clearance-candidate.md` | 17982 | `b1203d51676cb7ac8676e0f33c7769da2a599f93b2e57560b073f930fc41b0fe` |
| `Simulator/wksim_planning/ego_exact_clearance.py` | 38854 | `8b1d2dd8c097447d32d5d4f22b5827f8712ac84c9de0e963983d24e73efd46ea` |
| `validation/test_ego_exact_clearance.py` | 56737 | `d3541280c8d03127b047a2c7d67ce5581b6ff0c4dd0378b96209550ff762ae17` |
| `Simulator/wksim_planning/ego_scene_admission.py` | 34774 | `f88fa9c67b0410b8d7e65145008b21173959c03b6f0773c841cdb5e7e3ff7eca` |
| `Simulator/wksim_runtime/planner_transport_pump.py` | 32032 | `c9b541b4fb6112b09aacdb405838aa2f3c8935e144a21067f9c420f473279d27` |

终稿不是 repair3/postrepair3 合同 `7b1e9bfa…`，也不是第一次文档修补的错误 R2 收据 `a6637ed8…`。Python/测试/封印哈希相对 postrepair3 未变。HEAD 仍为 `6eafdf9c0b734db07a9fe790c86b409d3468c10b`。无 commit / stage / reset / clean。

## 先验 delta 一致性

`cursor-g3-exact-docfix2-delta-review-20260914-01` 两端结果内部一致，且与当前工作树对齐：

| 检查 | Windows | Ubuntu-22.04 |
| --- | --- | --- |
| schema | `wksim.g3-exact-docfix2-delta-review.semantic-check.v1` | 同 |
| 计数 | 55 / 55，failed 空 | 同 |
| 裁决 | PASS | PASS |
| 检查名 / ok 序列 | 相同 | 相同 |
| 嵌入哈希 | 与当前终稿一致，含 `b1203d51…` | 同 |
| live 数字 | 相同 | 相同 |
| `stale_receipt_trusted` | false | false |
| 捕获 | `passed 55 / 55 verdict=PASS` | 同上，且 `semantic_exit=0`，Ubuntu 22.04.5 LTS，HEAD 对齐 |

delta 捕获与 JSON 互相印证。Windows 捕获是短 stdout；Linux 捕获带包装元数据。两者都记录 55/55 PASS，不构成不一致。

先验 delta 工件 SHA-256：

| 路径 | SHA-256 |
| --- | --- |
| `check/results-windows.json` | `35e0fdffa05da8594ce05b81d88ae5b7bdb5a81f512452e889e27a0781354ee1` |
| `check/results-linux-ubuntu-22.04.json` | `c000c96425460553b2de79f681899df837c84cade1bdf6087a96b61a43a43154` |
| `captures/check-windows.txt` | `c54a01bf3cfc9efd152b56630381a7e38d1536542dd13b3e6875263963803129` |
| `captures/check-linux-ubuntu-22.04.txt` | `7fffe51d629ab23d4144de26af0466f5c9d72c7c712780f11ad51683664b4c39` |
| `freeze/hash-start.json` | `e172c8111f7b58dc610bf60d7dc10a6d2bbfa5070efbc7f1d3a3943504cc2f7b` |

第一次文档修补收据 `cursor-g3-exact-docfix-20260914-01` 把 R2 写成 “certified upper or lower bracket”，哈希 `a6637ed8…`。delta 与本终审均不信任该收据。

## 先前完整 G3 PASS（postrepair3）

`cursor-g3-exact-postrepair3-review-20260914-01` 对同一 Python/测试哈希给出 **PASS**（721/721 hostile，53/53 候选套件，179 四文件，两端平台）。当时合同仍是 `7b1e9bfa…`，并记录两则文档 P3：

* **P3-DOC-R2**：未闭合证书被写成总是 `indeterminate`；实际可用上界给出 conclusive `rejected`。
* **P3-DOC-576**：把不安全 `alternating_witness()` 写成 safe，并把 `57.6 m/s` 写成密采样极大。

本终审确认这两则已被终稿 `b1203d51…` 关闭。代码侧 P3-N1（n-partition 门已实现但不是公开 API 可演示裁决）仍在，不属于本次文档 delta。无 P1 / P2。

## 终稿合同极性

独立读合同与模块决策路径，并做直线夹具快速抽查（不构造 200 跨度交替见证）：

| 性质 | 合同 | 源码 | 本抽查 |
| --- | --- | --- | --- |
| 只有认证**上界**证明违规 | “if a certified upper bound already proves a clearance violation” → conclusive `rejected` | `obstacle_fail` / `inset_fail` 用 `span_upper_*` | 穿障未闭合：`rejected`，`upper = -0.100 m < 0.30`，`admitted=False` |
| **下界**只用于准入 | “every span's **lower** bound `>= required`”；“only `lower >= required` admits” | `span_ok` 用 `span_lower_*`；`admitted=True` 仅 `STATUS_ADMITTED` | 刚过门槛未闭合：`lower_net = -0.401` 且 `upper_net = 0.349` → `indeterminate`，不是违规证明 |
| 未闭合永不准入 | “An unclosed certificate is never admitted”；否则 `indeterminate` | `base(..., admitted=False)`；未决走 `STATUS_INDETERMINATE` | 未闭合拒绝 / 未闭合安全 / 刚过门槛：全部 `admitted=False` |
| `tolerance_met != admitted` | “It is not equivalent to `admitted`” | `tolerance_met` 只表示跨度闭合到声明分辨率 | 闭合拒绝与带宽：`tolerance_met=True` 且 `admitted=False`；准入才两者皆真 |

已删除的错误句：“an unclosed certificate is indeterminate rather than admitted”、“certified upper or lower”、“dense maximum of 57.6”、“*safe* curve has V = 120”。`safe curve` 只出现在两行工作帽表。

## 交替见证数字 / 57.6

终稿把磁盘夹具写成：`alternating_witness()`，真净间隙约 `0.20 m`，**unsafe**，`rejected`，60200 次求值，`V = 120 m/s`，真导数上确界 `60.0 m/s`，比值 `2.00`。`57.6 m/s`（比值 `2.08`）只作为共振 1001 点网格 `u = 0, 0.001, …, 1.0` 的观察，并写明不得当作密采样极大。

这些数字与 postrepair3 独立测量及 delta 两端 live 块一致（`V ≈ 120`，`midspan_supremum ≈ 60`，`ratio ≈ 2.00`，`evaluations = 60200`，`status = rejected`，`grid_1001 = 57.6`，非共振网格靠近 60）。本终审不重跑该 60200 路径。

## 本审查亲自执行的运行

| 平台 | 命令 | 结果 |
| --- | --- | --- |
| Windows，Python 3.13.11 | `python …/check/spotcheck.py --label windows --write` | **107 / 107 PASS** |

抽查覆盖：当前哈希、delta/冻结/捕获一致性、合同禁/必现短语、源码极性、直线夹具决策。未重跑 55 项 live 交替路径、hostile 721、pytest 或 unittest。

## 非声称

不关闭 #102 / #39 / G3 / Full，不批准把该谓词升为默认严格门。无动力学、跟踪误差、控制器滞后、力、冲量、地形、规划器、套接字、发布或飞行安全声称。未做 native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83。无 Git 或 GitHub 变更。
