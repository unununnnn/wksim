# 比较器修复独立评审（claude-comparator-repair-review-20260913-01)

**评审 SHA**（作者后续改动不在其内）:
- `tools/compare_first_step_trace.py` `7f7be184e2e31c6dbb9a4a198b4c313f7cef5b72f8f18abd958606c144eefc9f`
- `validation/test_compare_first_step_trace.py` `20b4442778ec5263d383e81b324ae8c39c383b4d5662d8c47d35282825b33c91`

## 结论：无阻断；一项非阻断语义发现

### 修复正确性（逐项核实）

1. **canonical hex**:`canonical_f64_hex` 在解码前强制"恰 16 位十六进制 + 可选小写 0x";`bytes.fromhex` 的空白跳过旁路已封死。我的真实比较伪证：把真实轨迹 stage state_hex 首项改 `0X` 前缀 → rejected；空白/短长/非字符串由作者 CanonicalFormTests 覆盖。
2. **精确整数序位**:stage/k/mrdivide_seq/is_major/nXc 全部 `type(x) is int`。**有效双 major 正例先于单 k 变异被承认**(`test_two_major_fixture_is_admitted_before_mutation` → aligned)，随后的 1.0/True/"0" 变异各自被拒。我的补充:nXc=True(bool）拒；is_major=False(False==0，作用于 minor 行）拒——与作者的 True==1 用例互补。
3. **nXc 36.0**：浮点 36.0 拒绝（作者），bool True 拒绝（我的）。
4. **solve 用真实 run-05**:REFERENCE_SOLVE=run-05,TARGET_SOLVE=g6-target-mrdivide；禁用探针与旧 run-03 的兼容/拒绝双向保持。
5. **映射不变**:BLOCK_MAP (6,9)(10,12)(13,15)(16,18) 与 comparison-v2.json 的 target_indices 逐对相同；EXPECTED/SOLVE_TIMES 与 SOLVE_MAJOR_FLAGS 与边界文档"五次事件 0、0.0005、0.0005、0.001、0.001"一致；PQR_DERIV_SLICE (10,13) 不变。
6. **真实差异不变（当前 SHA 重跑，非信托 artifact)**：留存 `comparator-result-v2.json` 由旧比较器 `569742b6…` 生成，与当前 SHA 不同，故我重跑：原始 target→run-03 仍得最早差异 p,q,r stage2 idx1 `bc56d4db33a987b8`→`…b9` 1ULP;solve target→run-05 恰一处 seq2 1ULP；候选轨迹→run-05 aligned 且零差异（候选修复效果不变）。留存轨迹字节 SHA 与 v2 artifact 绑定一致（已核）。
7. 作者套件 52/52 OK 无跳过；CLI 哈希绑定与排他输出经我独立冒烟通过。

### 发现（非阻断，建议作者定夺）

**solve 操作数不等不拒绝**：把 solve seq2 的 `numerator_hex[0]` 改为 `0x3ff0000000000001`，当前比较器返回 status=aligned，仅在 `solve.rows[2].numerator_equal=false` 中体现（matrix_equal 仍 true，真实 1ULP 差异照常报告）。鉴于本比较器的存在目的正是验证"同操作数 1ULP",aligned 判定可携带操作数不等，且操作数差异只得布尔而非文档字符串承诺的"逐位 hex 对+ULP"。建议：操作数不等时拒绝，或明确文档化 aligned≠同操作数。复现见 `review_checks.py::test_operand_mutation_is_surfaced` + 本目录 `operand-probe 输出`（见下）。

### 限制

- major_output 行只校验 k 序位/位置，载荷（Vehicle60 等）不参与比较。
- target 的 k0 输入与参考输入不做显式相等检查（输入不同会经数值差异显现）。
- aligned 仅限 13/36 映射态的结构对齐，非 G6/R1 通过；本评审未扩展 G6 合同。
- 我的伪证仅覆盖当前 SHA;author 若再改，须重钉。

## 交付物 SHA-256

- `review_checks.py`（独立检查，10/10 过）：见 `shas` 下记
- 本报告：见交付消息

独立检查清单（全部真实 compare、无 mock oracle)：留存轨迹未变、原始差异不变、solve 差异不变、候选零差异、0X 前缀拒、nXc bool 拒、probe dropped_events=1 拒、is_major False 拒、operand 变异语义记录、CLI 冒烟。
