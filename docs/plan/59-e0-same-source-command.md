# #59 同源 e0 数值验收命令接缝（fail-closed 入口）

2026-09-11。本切片交付 #59 路线中“SLX 11.8 normal 对同源 11.8 native”唯一可执行命令的**入口接缝**：先验证新合同 schema/identity/逐量预算，再决定是否可达执行阶段。本切片**不实现**参考/候选执行与逐量比较本身，也不冻结任何预算。

## 交付物（仅 3 个新文件，不改旧 R1）

- `tools/run_e0_same_source_conformance.py` — fail-closed 入口 + 纯解析/对齐层。
- `validation/test_e0_same_source_conformance.py` — 26 项单元测试，纯 Python、不启动 MATLAB/build、不读真实模型。
- 本文档。

明确不复用旧入口：`tools/run_numerical_conformance.py` 硬绑定旧 11.0 目标构建（`BUILD=/root/wksim-major-recorder-j_3guvtn/build.json`、`EXE_SHA c685817a…`）与冻结合同 `numerical-conformance-v1.json`（`CONTRACT_SHA 23d72e26…`），其 `compare()` 强制 `rule=='finite_binary64_value_equal'` 且预算全 0。旧合同一字未改。

## fail-closed 次序（关键不变量）

入口 `run(contract_path)` 的顺序保证：

1. **先验证新合同**（`validate_contract`）：仅读取合同文件本身，绝不触碰 MATLAB/native。校验：
   - 路径拒绝 = 冻结 R1 合同（`FORBIDDEN_CONTRACT`，按 resolve 后相等判断）；
   - `schema_version` 必须是整数 1、`status=='frozen'`、`contract_id` 非空且不得等于 R1 id `wksim-e0-fixed-reference-native-preservation-v1`；
   - `identity` 块齐全（reference/target revision、reference_engine、target_profile 均为非空字符串，slx/init 各带非空路径和 64 位小写十六进制 sha256）；
   - `sampling`：`array_lengths` 恰为 `Vehicle60=60/Sensor30=30/GPS30=30`、`fixed_step_s==0.001`、k 范围 0..500；
   - 逐 observable：必备字段 `observable, source_mapping, unit, frame, datum, sample_phase, metric, abs_budget, rel_budget, rms_budget, derivation, domain, approval, contract_sha256, array, indices`；三个预算须为有限非负数；`approval` 必须恰为 `'approved'`；`contract_sha256` 为 64 位小写十六进制，`array`/`indices` 合法、非空且不重复；
   - **标量覆盖必须恰为 120**（少一个即阻塞）。
2. 若**任一** observable 缺 abs/rel/RMS 预算，或 `approval != approved`，或 identity/schema 不完整 → 返回 `status='blocked'`、`physical_accuracy=False`、`g6_acceptance=False`、`matlab_launched=False`、`native_launched=False`、`execution_attempted=False`，并列出全部 `blocking_reasons`。**绝不启动 MATLAB/native，绝不报 pass。**
3. 仅当合同完全供给且 approved 后，执行/比较阶段才“可达”——但本切片刻意不实现它，返回 `status='execution_not_implemented'`，仍 `physical_accuracy=False`、不报 pass。

退出码：`blocked` → 2；`execution_not_implemented` → 3。本接缝没有 `pass` 或退出码 0 路径，外层自动化不能把“合同已就绪但执行尚未实现”误判为数值通过。

## 纯解析/对齐层（可独立测试，严格拒绝）

复用既有数据格式，不重发引擎：

- **normal 参考**：`export_model_reference.m` 写出的 `<Array>.f64`（501 行 little-endian binary64，行 = `[time, v0..vW-1]`，行主序）。`parse_reference_f64` 强制：字节数恰为 `501*(W+1)*8`、时间网格 `k*0.001`（容差 1e-12）、时间单调、全部有限非布尔。
- **native 候选**：`build_generated_e0_major.py`/`major_model_recorder.cpp` 的 `record.jsonl`。`parse_native_record` 强制：恰 503 条（start+501+end）、完整且可选择精确比对的嵌入式 source identity、起止 schema/计划时刻、存在且 `status=='complete'` 的 `major_recorder_end`（attempted/returned/emitted 各为 int 501、`engine_end_s==0.501`、`comparison_end_s==0.500`）、501 条样本按 k/call 顺序、`step_status=='complete'`、每步 input/before/after 时钟与 1ms 网格一致、`major_capture_count==1`，且每条 `major_root_outputs` 含 60/30/30 共 120 个有限非布尔值。
- **对齐**：`align(reference_by_array, native_by_array, observables)` 产出逐标量 `(reference[501], native[501])` 对，按 observable 的 `array`/`indices` 索引；任何覆盖/形状不匹配即 `Reject`。

所有拒绝经 `Reject` 异常映射为非通过结果；解析层不执行任何模型。

## 本切片未交付 / 禁止边界

- **未冻结任何预算**：`abs_budget`/`rel_budget`/`rms_budget` 仍全部待有依据推导。禁止用旧 R1 观测差值或本次候选差值乘系数反推；禁止套用 RK4 O(h^4) 阶数或网格收敛作预算。
- **未实现**参考/候选执行与逐量预算比较阶段；该阶段需在新合同 approved 后另行分配写入范围，且仍须满足原合同的拒绝边界（缺身份/错格点/少样/非有限/布尔伪数值/缺终态/随机相位未证/预算未冻结均不得通过）。
- 不改 `numerical-conformance-v1.json`、不改 `run_numerical_conformance.py`、不改 `build_generated_e0_major.py`、`export_model_reference.m`。
- 本接缝通过 ≠ 物理精度通过 ≠ G6/Full 通过；`physical_accuracy` 恒为 False。
- 未 git 提交/推送/issue 写入；未启动 MATLAB/build/仿真。

## 验证

```powershell
python -B -m unittest validation.test_e0_same_source_conformance -v
```

26 项全部通过（纯解析/对齐/入口；无 MATLAB/build/真实模型）。
