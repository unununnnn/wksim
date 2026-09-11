# #59 同源 e0 数值验收命令接缝（fail-closed 入口）

2026-09-11。本切片交付 #59 路线中“SLX 11.8 normal 对同源 11.8 native”唯一可执行命令的**入口接缝**：先验证新合同 schema/identity/逐量预算，再在完整执行身份存在时编排 normal→native→离线比较。本切片不冻结任何预算。

## 交付物（仅 3 个新文件，不改旧 R1）

- `tools/run_e0_same_source_conformance.py` — fail-closed 入口、可注入的 normal/native 编排、解析/对齐层。
- `validation/test_e0_same_source_conformance.py` — 63 项纯 Python 单元测试，不启动 MATLAB/WSL/build，不读真实模型。
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
3. 仅当合同完全供给且 approved 后，才校验 execution block、所有输入/脚本/模型/manifest SHA 和 staging 文件。MATLAB 本体按合同 SHA 校验；native executable 在 WSL 内按 filename、regular-file、execute bit、size 和 SHA 实测并与 build manifest 交叉核对。执行身份缺失或不一致仍返回 `status='blocked'`，且不创建 evidence 目录。
4. 所有预检通过后才在同一父目录的临时 staging tree 中准备证据，完整复制并复核后一次 rename 为最终 evidence 目录；准备失败会清理临时目录。随后依次启动 normal MATLAB 与 native major recorder；两侧输出、输入、终态和 source identity 全部有效后，才进入 `align()`/`compare_aligned()`。

退出码：`blocked`/`invalid_run` → 2；`numerical_failed` → 1；`declared_cases_pass` → 0。`declared_cases_pass` 仍只表示声明合同下的数值比较结果，不代表 physical accuracy 或 G6 通过。

## normal→native 执行编排

执行合同在新合同根部增加 `execution`：

- `case_id`、`input.path/sha256`、正好 501 行的 `k,time_s,inPWMs[16],TerrainIn15d[15]` CSV；
- `normal.matlab/matlab_sha256`、`normal.export_script.path/sha256`，以及至少包含 SLX、init、`parameter-bindings.json`、`readiness.json`、`dependencies.json` 的 `normal.stage_files`；SLX/init 的 SHA 必须与 `identity` 相同；
- `native.manifest.path/sha256`、`native.executable_sha256`、`native.wsl_executable`、可选 `native.wsl_distro`；manifest 中的 `source_identity` 和 executable SHA 必须完整且一致；
- `timeout_seconds`。

所有路径、文件存在性、文件 SHA、输入格点、native source identity、WSL executable 实体和合同文件 SHA 都在最终 evidence 目录创建前检查。执行阶段使用新目录和私有 `TEMP/TMP/MATLAB_PREFDIR`，不覆盖已有证据。Windows 侧进程超时后按独立 process group 回收整棵子进程树；native 同时由 WSL 内的 `timeout` 在期限后 TERM、5 秒后 KILL，并对 Windows 侧 reap 使用有界等待。

normal 命令固定为：

```text
D:/matlab/install date/bin/matlab.exe -wait -sd <evidence>/normal -batch export_model_reference
```

native 命令固定为：

```text
wsl.exe -d Ubuntu-22.04 --exec timeout --signal=TERM --kill-after=5s <timeout>s <native.wsl_executable> --record <wsl-input.csv>
```

`build_generated_e0_major.py` 只提供已构建 executable 和 manifest；新的 `run()` 不在执行阶段编译。normal 必须产出 `reference.json`、三个 `<Array>.f64` 和 `applied-input.f64`；native 必须产出现有 503 行 recorder JSONL。normal 的 `case/epoch/contract_sha256`、native 的输入原文与 source identity 必须与外层 manifest 和合同一致。

结果保存为 `result.json`，至少包含 `status/case_id/epoch/contract_sha256/input_sha256`、normal/native argv、cwd、退出码、超时、两侧实测 source/executable identity、原始输出路径、sampling、120 标量比较统计、失败计数，以及恒为 false 的 `physical_accuracy/g6_acceptance`。

## 纯解析/对齐层（可独立测试，严格拒绝）

复用既有数据格式，不重发引擎：

- **normal 参考**：`export_model_reference.m` 写出的 `<Array>.f64`（501 行 little-endian binary64，行 = `[time, v0..vW-1]`，行主序）。`parse_reference_f64` 强制：字节数恰为 `501*(W+1)*8`、时间网格 `k*0.001`（容差 1e-12）、时间单调、全部有限非布尔。
- **native 候选**：`build_generated_e0_major.py`/`major_model_recorder.cpp` 的 `record.jsonl`。`parse_native_record` 强制：恰 503 条（start+501+end）、完整且可选择精确比对的嵌入式 source identity、起止 schema/计划时刻、存在且 `status=='complete'` 的 `major_recorder_end`（attempted/returned/emitted 各为 int 501、`engine_end_s==0.501`、`comparison_end_s==0.500`）、501 条样本按 k/call 顺序、`step_status=='complete'`、每步 input/before/after 时钟与 1ms 网格一致、`major_capture_count==1`，且每条 `major_root_outputs` 含 60/30/30 共 120 个有限非布尔值。
- **对齐**：`align(reference_by_array, native_by_array, observables)` 产出逐标量 `(reference[501], native[501])` 对，按 observable 的 `array`/`indices` 索引；任何覆盖/形状不匹配即 `Reject`。

所有拒绝经 `Reject` 异常映射为非通过结果；解析层不执行任何模型。

## 纯离线逐量比较层（不执行 MATLAB/native）

`compare_aligned(aligned, observables)` 只消费 `align()` 已对齐的逐标量 `(reference[501], native[501])` 对，绝不读取引擎输出、绝不启动 MATLAB/native。

**冻结的唯一公式标识**：`metric` 字段必须恰为 `abs_le_a_plus_r_absref_with_rms_cap_v1`（`FROZEN_METRIC`）。任何其他 metric 标识在 `validate_contract` 即阻塞、在 `compare_aligned` 即 `Reject`。该标识对逐标量 `i` 冻结的判定为 `docs/plan/10-g6-remediation-contract.md` §49 已写公式：

- 逐点（pointwise）：`abs(x - r) <= A_i + R_i*abs(r)`，其中 `A_i=abs_budget`、`R_i=rel_budget`；
- 独立的 RMS 上限：`rms(errors) <= rms_budget`（rms_budget 与逐点预算彼此独立，逐点全过但 RMS 超上限仍判失败）。

逐标量输出：`max_abs_error`、`rms_error`、`first_pointwise_failure_k`、`pointwise_failed_count`、`rms_failed`、`failed_count`；汇总 `failed_values`（逐点失败值数）、`failed_conditions`（逐点失败值数加 RMS 失败条件数）与 `failed_scalars`。**aggregate 只能是 `numerical_failed` 或 `declared_cases_pass`**，且恒带 `physical_accuracy=False`、`g6_acceptance=False`——该数值标签不是 G6/物理精度通过。

严格 `Reject`：metric 非冻结标识；任一预算缺失/非有限/为负；reference 或 native 值非有限或为布尔；序列长度 ≠ 501；observable 或 aligned 重复映射同一 `(array,index)`；aligned 标量无对应预算或 observable 身份不符。两侧覆盖必须恰为同一组 120 个标量。

`run()` 已接线 normal→native→`compare_aligned`，但 launcher 和 WSL 路径解析器可注入，测试不会触发真实进程。任何合同、身份、预算或运行产物拒绝都会落到 `blocked` 或 `invalid_run`，不生成数值通过。

## 本切片未交付 / 禁止边界

- **未冻结任何预算**：`abs_budget`/`rel_budget`/`rms_budget` 仍全部待有依据推导。禁止用旧 R1 观测差值或本次候选差值乘系数反推；禁止套用 RK4 O(h^4) 阶数或网格收敛作预算。
- **执行仍受合同阻塞**：当前真实合同没有 120 个 approved 逐量 abs/rel/RMS 预算，尤其 56 个动态量仍未冻结；因此真实入口在任何 MATLAB/native 启动前返回 `blocked`。实现编排不等于取得预算，也不允许用观察差值反推预算。
- 不改 `numerical-conformance-v1.json`、不改 `run_numerical_conformance.py`、不改 `build_generated_e0_major.py`、`export_model_reference.m`。
- 本接缝通过 ≠ 物理精度通过 ≠ G6/Full 通过；`physical_accuracy` 恒为 False。
- 本切片未启动 MATLAB/WSL/build/仿真；测试只使用 synthetic contract、fake launcher 和临时目录。

## 验证

```powershell
python -B -m unittest validation.test_e0_same_source_conformance -v
```

63 项全部通过（合同校验、MATLAB/native 启动前实体复核、原子 staging、host/WSL 双层超时识别与进程树回收、注入的路径解析/normal/native 正例与失败边界、解析/对齐、逐量比较；无 MATLAB/WSL/build/真实模型）。
