# #59 G6 同源 e0 激活就绪性（same-source activation readiness）

**状态：BLOCKED（入口未就绪，0/120 预算获批）。** 2026-09-14，只读离线切片 `codebuddy-g6-same-source-activation-readiness-20260914-01`。本文件与配套离线单测 `validation/test_codebuddy_g6_same_source_activation_readiness.py` 构成最小同源激活就绪性证据对：只描述**已实现**的入口预检次序、当前 fail-closed 阻塞项、未来已授权命令形态、期望输出/证据字段与确定性 READY/BLOCKED 规则。本切片不启动 MATLAB/native/build/仿真，不填造任何预算，不构成任何批准。

- 对象入口：`tools/run_e0_same_source_conformance.py`（#59 "SLX 11.8 normal 对同源 11.8 native" 入口接缝；不是旧 R1 跨版本重跑入口）。
- 本文件不绑定 HEAD 精确值：只要求 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`、`6eafdf9c0b734db07a9fe790c86b409d3468c10b`、`31e5b65f5448c5558450d16d0f46da0ef0f0a03c` 是当前 HEAD 的祖先；不要求当前 HEAD 等于其中任何一个（ancestry 由配套单测 fail-closed 验证）。
- 就绪性不是数值通过：R1 冻结结果保持 `numerical_failed`，#59、#84、G6、Full 保持 open/not-closed。

## 1. 已实现预检次序（exact implemented preflight order）

入口 `run()` 对给定合同路径严格按以下次序执行；任一步失败都在启动 MATLAB/native 之前返回 `blocked`（已进入执行阶段后的失败返回 `invalid_run`）：

1. `validate_contract` — 只读取合同文件本身，绝不触碰 MATLAB/native。
   - `schema_version` 必须为整数 1；`status=='frozen'`；`contract_id` 非空且不得等于 R1 id `wksim-e0-fixed-reference-native-preservation-v1`。
   - `identity` 六项齐全（reference/target revision、reference_engine、target_profile、slx、init）；`slx`/`init` 各带非空路径与 64 位小写十六进制 sha256。
   - `sampling`：`Vehicle60=60`/`Sensor30=30`/`GPS30=30`、`fixed_step_s==0.001`、`k_first=0`/`k_last=500`。
   - 逐 observable 必备 16 字段；abs/rel/RMS 三预算有限非负；`approval=='approved'`；`metric` 恰为 `abs_le_a_plus_r_absref_with_rms_cap_v1`；`array`/`indices` 合法、非空、不重复；标量覆盖恰为 120。
2. `validate_execution` — 仅在 `blocking_reasons` 为空后才可达；校验执行身份但不创建文件、不启动进程。
   - `execution.case_id`、合同 SHA 自校验、501 行 × 33 字段输入 CSV（`k,time_s,inPWMs[16],TerrainIn15d[15]`）、k 序列与 1 ms 时间网格、PWM∈[0,1]。
   - `normal.matlab`+`matlab_sha256`、`normal.export_script`、`normal.stage_files` 必含 SLX/init/`parameter-bindings.json`/`readiness.json`/`dependencies.json`，且 SLX/init 的 SHA 与 `identity` 一致。
   - `native.manifest` + `native.manifest.source_identity`（14 字段、8 个 sha256）、`executable.filename/sha256/size_bytes`、`wsl_executable`、`wsl_distro`、`timeout_seconds`。
3. `_verify_native_executable` — 在选定 WSL distro 内实测 `test -f`、`test -x`、`sha256sum`、`stat -Lc '%s\t%a'`，与 build manifest 的 filename/sha256/size 交叉核对；不一致立即 blocked。
4. `_prepare_execution` — 在证据父目录下建立私有 staging tree，逐文件复制并复核 SHA，最后单次 `rename` 发布最终 evidence 目录；准备失败清理临时目录且不发布任何证据。
5. `_launch_process`（normal 侧） — 启动前再次核对 MATLAB SHA；使用独立进程组，Windows 侧超时按 `taskkill /T /F` 回收整棵进程树。normal 命令固定为 `matlab.exe -wait -sd <evidence>/normal -batch export_model_reference`。
6. `_validate_reference_outputs` — 要求 `reference.json` 的 case/epoch/contract_sha256 与外层 manifest 一致；`<Array>.f64` 恰为 501 行 little-endian binary64（行 = `[time, v0..vW-1]`）、时间网格 `k*0.001`；`applied-input.f64` 与输入 CSV 字节一致。
7. `_verify_native_executable` — native 启动前再测一次可执行实体（防止发布后被替换）。
8. `_launch_process`（native 侧） — `wsl.exe -d <distro> --exec timeout --signal=TERM --kill-after=5s <timeout>s <wsl_executable> --record <wsl-input.csv>`；WSL 侧退出码 124/137 识别为 `wsl_coreutils_timeout`，宿主侧超时识别为 `host_process_deadline`。
9. `_validate_native_inputs` — native `major_recorder_start.input_csv` 必须与输入 CSV 字节相同，且 501 条样本的 inPWMs/TerrainIn15d 与输入逐行一致。
10. `parse_native_record` — 恰 503 条记录（start + 501 sample + end）、嵌入式 source identity 与 manifest 精确相等、`major_recorder_end.status=='complete'`、attempted/returned/emitted 各为 501、`engine_end_s==0.501`、`comparison_end_s==0.500`、每步 120 个有限非布尔值。
11. `align(` — 按 observable 的 `array`/`indices` 产出逐标量 `(reference[501], native[501])` 对；覆盖必须恰为 120，任何形状/覆盖不匹配即 `Reject`。
12. `compare_aligned` — 只消费已对齐对，绝不读取引擎输出：逐点 `abs(x-r) <= A_i + R_i*abs(r)`，并独立要求 `rms(errors) <= rms_budget`；聚合标签只可能是 `numerical_failed` 或 `declared_cases_pass`。
13. `_execution_result` — 写 `result.json`（两侧 argv/cwd/退出码/超时/source identity/原始输出路径、采样、120 标量统计），恒定 `physical_accuracy=False`、`g6_acceptance=False`。

退出码：`blocked`/`invalid_run` → 2；`numerical_failed` → 1；`declared_cases_pass` → 0。`declared_cases_pass` 只是声明合同下的数值比较结果，不是物理精度或 G6 通过。

## 2. 当前 fail-closed 阻塞项（current blockers）

当前既没有完整获批的同源合同，也没有 120 个获批的逐量预算，因此 READY 的四项条件全部不成立，入口在任何模型启动之前返回 `blocked`：

- **合同缺失**：仓库中不存在新的同源合同 JSON；任何真实调用首先在 `validate_contract` 以 `new contract file not found` 阻塞（若换成不完整合同，则以 schema/identity/逐量预算/覆盖不到 120 的原因阻塞），绝不启动模型。
- **预算全缺（0/120）**：`validation/e0-budget-approval-provenance-20260914.json` 记录 `slots_total=120`、`slots_dynamic_candidate=56`、`slots_policy=64`、`slots_with_numeric_budget=0`、`slots_with_approval_identity=0`、`slots_approved=0`、`slots_blocked=56`、`slots_pending_owner_policy=64`、`external_owner_records=0`、`external_derivation_records=0`、`dynamic_slots_with_committed_frame_binding=0`、`dynamic_slots_with_committed_datum_binding=0`。
- **frame/datum 仅部分绑定**：`validation/e0-frame-datum-binding-20260914.json` 记录 `frame_bound=25`、`frame_unresolved=31`、`datum_bound=10`、`datum_unresolved=46`、`owner_decision_count=24`（`slot_count=56`）；24 项 owner 决策全部 not_made。
- **R1 不可挪用**：冻结合同 `Simulator/wksim_core/numerical-conformance-v1.json`（`contract_id=wksim-e0-fixed-reference-native-preservation-v1`，SHA256 以 `23d72e26` 开头）120 槽 `absolute_budget=0`/`relative_budget=0`、`rule=finite_binary64_value_equal`；入口按 resolve 后路径相等直接拒绝把它当作新合同。
- **语义未验证**：3 个 schedule_metadata 时间槽、四元数方向编码、GPS 航向、海拔基准、eph/epv 语义等尚无已承诺的 frame/datum/单位绑定；64 个 policy 槽（interface_metadata 5 + reserved_not_physical_coverage 59）不计作物理覆盖。
- **不得以缺省通过**：字段未知或缺预算依据时状态必须保持 blocked，不以 null、缺省值、占位值或空批准通过。

因此本切片结论是 **BLOCKED**：实现编排不等于取得预算；就绪性证据对本身不构成任何批准，也不关闭任何票据。

## 3. 未来已授权命令形态（future authorized command shape）

入口 CLI（以下只是参数格式；当前没有完整获批合同，故不是可运行的已批准命令）：

```text
python tools/run_e0_same_source_conformance.py <新合同路径> --output <新结果路径> --evidence-dir <新证据目录>
```

- `<新合同路径>` 必须指向**新**的同源合同文件，绝不能是 `Simulator/wksim_core/numerical-conformance-v1.json`。
- `--output` 写 `result.json`；`--evidence-dir` 必须是不存在的新目录（已存在即拒绝覆盖）；证据在私有 TEMP/TMP/`MATLAB_PREFDIR` 下准备。
- normal 固定命令：`D:/matlab/install date/bin/matlab.exe -wait -sd <evidence>/normal -batch export_model_reference`；MATLAB 本体按合同 SHA 校验。
- native 固定命令：`wsl.exe -d Ubuntu-22.04 --exec timeout --signal=TERM --kill-after=5s <timeout>s <native.wsl_executable> --record <wsl-input.csv>`。
- 只有第 1 节预检全部通过后才会到达这些启动点；本切片不执行其中任何一条，也不把本形态当作已批准合同。

## 4. 期望输出与证据字段（expected output/evidence fields）

evidence 目录（单次 `rename` 原子发布）至少含：`contract.json`、`input.csv`、`manifest.json`、`native-build-manifest.json`、`normal/`（staging 文件、`export_model_reference.m`、`reference.json`、`Vehicle60.f64`/`Sensor30.f64`/`GPS30.f64`、`applied-input.f64`、`manifest.json`）、`normal.stdout.log`、`normal.stderr.log`、`normal-process.json`、`native-launch-identity.json`、`native.stdout.log`、`native.stderr.log`、`native-process.json`、`result.json`，以及私有 `temp/`、`pref/`、`cache/`、`codegen/`。

执行路径 `result.json` 至少含：`status`、`case_id`、`epoch`、`contract_id`、`contract_sha256`、`input_sha256`、`execution_attempted`、`matlab_launched`、`native_launched`、`normal`、`native`、`sampling`、`comparison`、`scalar_count`、`comparisons`、`failed_values`、`failed_conditions`、`failed_scalars`、`physical_accuracy`、`g6_acceptance`；阻塞路径至少含 `status`、`blocking_reasons`、`scope`、`physical_accuracy`、`g6_acceptance`、`execution_attempted`、`matlab_launched`、`native_launched`。

- normal 侧：argv、cwd、退出码、超时标记、pid、起止时刻、`source_identity`、期望与启动前实测可执行 SHA。
- native 侧：argv、cwd、退出码、超时标记与来源、WSL 输入路径解析、`expected_executable`、`preflight_executable`、`prelaunch_executable`、`source_identity`。
- 采样：`fixed_step_s=0.001`、`k_first=0`、`k_last=500`、`array_lengths`。
- 逐标量：`observable`、`array`、`index`、`sample_count`、`max_abs_error`、`rms_error`、`abs_budget`、`rel_budget`、`rms_budget`、`pointwise_failed_count`、`first_pointwise_failure_k`、`rms_failed`、`failed_count`。

## 5. 确定性 READY/BLOCKED 规则（deterministic rule）

对给定的合同路径 C 与环境 E，就绪性判定是确定性的、fail-closed 的：

- `READY(C, E)` 当且仅当以下四项全部成立：① `validate_contract(C)` 不抛 `Reject` 且返回的 `blocking_reasons` 为空；② `validate_execution(C, contract)` 成功返回执行身份；③ native executable identity probe 的 `path/sha256/size_bytes/regular_file/executable` 与 build manifest 完全一致；④ `_prepare_execution` 原子发布 staging（evidence）目录成功。
- `BLOCKED(C, E)` 当且仅当上述四项中任一不成立；此时入口在任何模型启动之前返回 `status='blocked'`，并且恒定 `execution_attempted=False`、`matlab_launched=False`、`native_launched=False`，同时列出全部 `blocking_reasons`。
- 可复现性：同一 C 与 E 重复调用返回同一 `status` 与同一 `blocking_reasons` 列表；判定不依赖时间、随机数或环境细节。
- `READY` 不是数值通过，也不是物理精度或 G6 通过：`READY` 只表示入口可到达执行阶段。执行阶段的聚合标签只可能是 `numerical_failed` 或 `declared_cases_pass`，且恒定 `physical_accuracy=False`、`g6_acceptance=False`。
- 就绪性判定不能被补写材料替换：在四项之外补写预算、批准或 frame/datum 记录都不能把 `BLOCKED` 变成 `READY`。

## 6. 禁止的预算推导来源（forbidden derivations）

- 禁止从**已观测差值**（R1 旧差、本次候选差）反推或乘系数反推任何 abs/rel/RMS 预算。
- 禁止以 double **ULP**、浮点 epsilon 或机器精度作为逐量预算。
- 禁止用**噪声**幅值、随机源统计或默认传感器噪声当作预算依据。
- 禁止用 ODE4/**RK4** 的 O(h^4) 阶数或网格收敛阶反推误差常数。
- 禁止把 **SITL** 航点/落点门槛或飞行验收门槛改用为 G6 逐量动力学等价预算。
- 禁止把**控制接缝**（控制集成）预算行（倍率/驻留/恢复门槛）当作 G6 逐量预算。

上述六类都不足以给出可诚实冻结的非零物理预算；预算仍需按工况上的误差分析或校准/传感器规格与用途需求单独取得并获批。

## 7. 来源 pin（six tracked sources only）

本切片只 pin 以下六个**已跟踪**来源（按 `git show HEAD:<path>` 的字节计算 sha256/size），不多 pin 任何其它来源，也不把任何未跟踪的采样约定（reference sampling）文档作为依赖：

| path | bytes | sha256 |
| --- | --- | --- |
| `tools/run_e0_same_source_conformance.py` | 64513 | `8398100b7fb6b839e279afd6e8f8708e57e415450dbb6621acdc9ea9ecc46517` |
| `docs/plan/59-e0-same-source-command.md` | 10221 | `345caff0fd354717a64ed1dfac2c3ad33f87c72713cf3362483c395fb66b197e` |
| `docs/plan/10-g6-remediation-contract.md` | 9935 | `48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0` |
| `validation/e0-budget-approval-provenance-20260914.json` | 285820 | `2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d` |
| `validation/e0-frame-datum-binding-20260914.json` | 105018 | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` |
| `Simulator/wksim_core/numerical-conformance-v1.json` | 29846 | `23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0` |

六个来源都必须仍是 HEAD 上的跟踪文件，且其 HEAD blob 字节与上表 sha256/size 一致；工作树与 HEAD 不一致即视为漂移。

## 8. 非关闭声明（non-closure）

- R1 旧结果原样保留：`numerical_failed` 继续成立，不改判、不重跑、不抹除任何失败记录。
- 本文件不关闭 #59、#84、G6 或 Full 中的任何一项；`Full = not-closed`，G0–G6 全部 `not-closed`，`#59/#84/G6 = open`。
- 本文件不构成任何批准：`budget_approved=false`、`g6_acceptance=false`、`physical_accuracy=false`、`issues_closed=false`。
- 本切片只在离线状态下成立：未执行 MATLAB/native/build/仿真，未复用 #83，未触碰任何飞行路径。

## 9. 验证

```powershell
python -B -m unittest validation.test_codebuddy_g6_same_source_activation_readiness -v
```

仓库外临时索引模式（临时索引，真实索引不被写入）：

```bash
TMPIDX="$TMPDIR/wksim-tmpidx-g6ssar"     # 必须位于仓库之外
GIT_INDEX_FILE="$TMPIDX" git add -- \
    docs/plan/59-g6-same-source-activation-readiness-20260914.md \
    validation/test_codebuddy_g6_same_source_activation_readiness.py
GIT_INDEX_FILE="$TMPIDX" WKSIM_G6_SSAR_TEST_MODE=external-index \
    python -B -m unittest validation.test_codebuddy_g6_same_source_activation_readiness -v
rm -f "$TMPIDX"
```

两种模式都不执行 MATLAB/native/ROS/DDS/Unreal/构建，不读写共享 `.git/index`，不提交、不推送。
