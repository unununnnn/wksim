# C3G stage-2 操作数边界比较器

2026-09-14。纯离线比较器，只读已保留的 C3G 首步求解痕迹或专用 operand packet。它把已经记录的最早差异——`p,q,r` stage 2、derivatives index 1、1 ULP——收成一条 fail-closed 的操作数边界，不运行模型、MATLAB、ROS、native、飞控、UE 或构建，也不改既有文件。

本切片是新开发，不是 G6 或 Full 验收。#59 与 #60 仍 OPEN；R1 仍 `numerical_failed`。

## 比较什么

输入路径必须显式给出。比较器不搜索默认证据目录。

| 输入 | 身份 | 抽出的 stage-2 边界 |
| --- | --- | --- |
| 参考 `run-05/reference-first-step.json` | `case=C3G`，`pqr_input_probe` 第 3 个事件（order=3，t=0.0005） | 分子 residual[0..2]、Selector2[0..8]、Product2[0..2] |
| 目标 `g6-target-mrdivide-20260913/first-step-trace.jsonl` | start `case=C3G`，`mrdivide_seq=2` | 同上；结果还须逐位等于 stage 2 的 p,q,r 导数 |
| 专用 packet `g6-c3g-stage2-operand-boundary/v1` | `case=C3G`，`k=[0,1]`，`stage=2`，`index=1`，时间 hex `3f40624dd2f1a9fc` | 上述三项，外加 `M1[1]`、`Fd[0]`、`Sum1_a[1]`、`TT0gLR`、`Sum4_f[0..2]`、气动阻尼乘积 |

可选 `--documented-divergence` 绑定 `comparison-v2.json` 或精简记录：必须仍是 stage 2、`derivatives[1]`，且抽出的 Product2[1] 与记录 hex 一致。

已记录的 hex 对：参考 `bc56d4db33a987b8`，目标 `bc56d4db33a987b9`。冻结对角惯量与现有求解痕迹相同：`diag(0.0211, 0.0219, 0.0366)`。

## 观察与因果

`aligned` 只表示两端身份对齐并且 binary64 可以逐位/ULP 比较。分类只标注观察分支：

- residual 与 Selector2 相同、Product2[1] 不同 → `identical_operands_different_result`
- residual 已不同 → `residual_already_differs`
- Selector2 已不同 → `selector2_already_differs`
- 三者都相同 → `identical_operands_identical_result`

`causal.status` 恒为 `unproven`。相同操作数不能证明参考端 LAPACK 内部，也不能排除 libm 或未映射的 23 个状态。专用 packet 上的子项相等只说明这些 hex 相同，不是 M1/Fd/陀螺/阻尼的根因隔离。保留求解痕迹没有子项时标记 `subterms.status=unobserved`，不编造。

畸形 hex、非有限值、布尔序号、错误 case/stage/时间、残缺 packet、单边求解痕迹或格式错配一律 `rejected`。输出独占创建，字节即哈希。

## 命令

```text
python -B tools/compare_g6_c3g_stage2.py ^
  --reference validation/coordination/g6-reference-probe-20260913/run-05/reference-first-step.json ^
  --target validation/coordination/g6-target-mrdivide-20260913/first-step-trace.jsonl ^
  --documented-divergence validation/coordination/g6-target-first-step-20260913/comparison-v2.json ^
  --output <全新路径.json>
python -B -m unittest validation.test_compare_g6_c3g_stage2
```

## 未解除的 G6 阻塞

本工具只覆盖 B5 的求解边界观察。它不批准 120 个量的预算（B1）、不绑定 frame/datum（B2）、不裁定时间规则（B3）、不冻结新同源合同（B4），也不关闭 #59/#60 或宣称 G6/Full 通过。子项双引擎捕获、其余 23 态映射和完整 501 样本比较仍待后续独立切片。
