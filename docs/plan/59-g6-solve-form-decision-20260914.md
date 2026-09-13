# #59 G6/B5 求解形式决策包（PROPOSED，未裁决）

2026-09-14。本文与机器可读记录 `validation/e0-g6-solve-form-decision-20260914.json`（schema `wksim.59-g6-solve-form-decision.v1`）成对交付，离线自测为 `validation/test_e0_g6_solve_form_decision.py`。回放原件在 `validation/coordination/cursor-g6-solve-form-20260914-01/`。

本切片是新开发，只覆盖 B5 的求解形式观察和对角候选复核。它不是 ADR，也不是所有者决定：#59、G6、Full 仍开放；`g6_acceptance=false`，`physical_accuracy=false`；R1 仍 `numerical_failed`。

## 检出身份

| 项 | 值 |
| --- | --- |
| 工作类别 | new-development |
| cwd / 分支 | `C:\Users\PC\Documents\odid编译\wksim` / `main` |
| HEAD | `768526aafa1e48c342c5c8840a9154e8ed90f68d` |
| 基线祖先 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 |
| 独占文件 | 本文、`validation/e0-g6-solve-form-decision-20260914.json`、`validation/test_e0_g6_solve_form_decision.py`、`validation/coordination/cursor-g6-solve-form-20260914-01/**` |
| 未改 | 比较器、R1 合同、同源入口、既有对角候选证据、其他 `59-e0-*`、#26/#33/#9 |

## 从源重算并钉死的三份追迹

哈希均对当前工作树字节重算，并与 HEAD blob 一致。

| 身份 | 路径 | SHA256 |
| --- | --- | --- |
| 参考 run-05 | `validation/coordination/g6-reference-probe-20260913/run-05/reference-first-step.json` | `72ff7d8eaeee7854bf026d19a7ee37f38c061764ce5369d0dd5845b1aa084c62` |
| 目标 mrdivide（除法形式） | `validation/coordination/g6-target-mrdivide-20260913/first-step-trace.jsonl` | `9cee60eb5b3e5ccc96730f13423f5e0fa07de19654a481d32e9e885953f4bed3` |
| 对角求解候选 | `validation/coordination/g6-diagonal-solve-candidate-20260913/first-step-trace.jsonl` | `5e89b720dac275a4980df1881aae2dfde76d223ad9a0bc8dbeba15edaa1e1d09` |

独立回放（只读调用既有比较器，不改工具）：

| 回放 | 状态 | SHA256 |
| --- | --- | --- |
| run-05 vs mrdivide | `aligned` | `bb45b0213dd9966c27e135bd173ebad5e250bdd51ae8cf108b0aa11ab8c2932d` |
| run-05 vs 对角候选 | `aligned`，最早差异 `null` | `56a611f96f72e6bce2a5b4bd612105cc88a4c2208de2918c16339e21de2eabbd` |
| C3G stage-2 操作数边界 | `aligned`，`identical_operands_different_result` | `07b5b6c07060417151470b48ddf0510920977c4101718ab7156d3b36ff2ee634` |

`aligned` 只表示结构可比较且 binary64 已逐位/ULP 对照，不是数值验收或 G6 通过。

## 已核验的判别点

五次求解的分子与 Selector2 全部逐位相同。**唯一求解结果差异**在 pair 2 / `mrdivide_seq=2` / ODE4 stage 2 / `derivatives[1]`（q）：

| 端 | hex | 相对参考 |
| --- | --- | --- |
| 参考 Product2[1] | `bc56d4db33a987b8` | — |
| 除法 / mrdivide | `bc56d4db33a987b9` | 1 ULP |
| 对角候选 | `bc56d4db33a987b8` | 0 ULP |

Selector2 为冻结对角 `diag(0.0211, 0.0219, 0.0366)`，六个非对角元均为 0。对实际 pair-2 操作数 `u0[1]=bc000013449033b2`、`u1[4]=3f966cf41f212d77` 做离线 IEEE-754 计算：直接除法得到目标 hex，乘以倒数得到参考 hex。这是求解形式观察，不是参考 LAPACK 内部证明。

对角候选在 13 个已映射刚体状态、四级导数、末态和五次求解上与参考逐位相同。除法形式仍把差异传播到后续映射态（q 块 2 处、pqr 块 2 处、ubvbwb 1 处）。

## 未观察域

- 36 个连续状态中 **23 个未映射**。
- **一例**（仅 C3G）、**一步**（仅 k=0→1）。
- **仅对角惯量 J**；非对角/次正规/回退路径未实测。
- 残差子项（M1/Fd/陀螺/阻尼）在保留求解痕迹上为 `unobserved`。
- C0/C2G、其余 500 个 major 样本、同源 Sensor30[10] 两处差异均不在本包。

## 恰好三个所有者选项（均未选）

1. **采用对角分支**：对有限非零对角惯量统一使用乘以倒数。
2. **保留除法，并用另行批准的预算吸收 1 ULP**：不改当前生成求解，也不在本包填写预算。
3. **推迟**：不改求解形式，也不写预算。

`owner_decision.state = not_made`，`chosen_option = null`。

## 对 B1 / B4 的影响（不为所有者代选）

| 选项 | B1（120 个量的预算，当前未批准） | B4（新同源合同冻结，当前未冻结） |
| --- | --- | --- |
| 采用对角分支 | 若候选采用该分支，本例首步已映射 pair 2/index 1 的 1 ULP 将不再出现；这不批准其余 120 槽，也不覆盖其他工况或 23 个未映射态。禁止把“消失的 ULP”反推成预算。 | 候选算术将不同于当前生成 mrdivide 函数体。日后冻结 B4 必须写明候选是否含此诊断分支。本包不冻结 B4。 |
| 保留除法并吸收 1 ULP | 必须另有依据并获批的逐量预算才能吸收该 ULP。本包不写、不推导、不批准该预算，也禁止用观测到的 1 ULP 当预算值。 | 日后 B4 可以继续记录当前除法形式。B4 仍未冻结；缺批准预算时同源入口仍 blocked。 |
| 推迟 | B1 保持未批准。 | B4 保持未冻结。 |

## 失败边界

畸形 hex、错误 case/stage（`identity.case` 必须恰为 `C3G`，`identity.stage` 必须恰为 `2`）、非对角 Selector2、求解形式与钉死 hex 不符、缺 pin、额外 pin、未知选项键、第四个选项、未知顶层键、`B1.current` 不是 `unapproved`、`B4.current` 不是 `unfrozen`、篡改哈希，一律 `rejected`。`g6_acceptance` 与 `physical_accuracy` 必须保持 false。`fail_closed_on` 含 `budget_or_contract_freeze`。

## 验证

```powershell
python -B -m unittest validation.test_e0_g6_solve_form_decision
```

不启动模型、MATLAB、ROS、native、飞控、UE、构建或 #83，不改工单，不 git add/commit/push。
