# 对角求解候选独立审查（2026-09-13，只读）

对象：`validation/coordination/g6-diagonal-solve-candidate-20260913/`（prepare.py、
candidate-command、compile/run-result、trace、comparison），对照
g6-target-mrdivide-20260913 与参考 run-05。未改实现、未跑 native/构建、无嵌套/Git。

## 核验结论（逐项）

- **配方正确性**：prepare.py 的插入段只对"全部非对角恰为 0、三对角元有限且非零、输入有限"的统一对角矩阵取倒数相乘；任一倒数非有限则**回退原通用求解**；原函数
  字节保留（`insertion_removed_restores_baseline` 且断言单次插入/移除复原）✓。
- **无特判**：插入段无时间/分量/输入特判，只有结构+有限性条件 ✓。
- **结果**：候选 seq2 q 输出 `bc56d4db33a987b8`，与参考**逐位一致**（v2 的
  1ULP 差异消除）；comparison：240 major、13 映射态/导数、5 次 solve 与参考
  逐位一致，differences=[]、bit_differences=0 ✓。
- **原件链**：mrdivide trace（`9cee60eb…`）与 run-05 参考（`72ff7d8e…`）哈希
  未变 ✓；compile/run 均 exit 0、PGID 678 清空 ✓；候选 command 独占创建 ✓。

## 阻断/边界

- `g6_acceptance=false`、`status=diagnostic_only` 如实：单步成功**不是** R1/G6
  通过；只证明"对该组实际有限非零对角矩阵，乘倒数与直接除法在此 1ULP 上不同"，
  不证明参考内部算法，不覆盖其余 23 状态或其它时刻。
- 候选的负零/次正规/超范围边界输入与通用回退路径未实测（本步输入均在界内）。

源 SHA：prepare.py 见 candidate-command `candidate_recipe_sha256`；
candidate trace `5e89b720…`；comparator-result aligned。

另：main-review-v2 已更正旧负例——真正参与比较的 PostDerivatives dtype 负例
本就拒绝；未参与比较的 PostOutputs.derivatives 不构成数值漏洞，本审查不重复
宣称。
