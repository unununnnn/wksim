# 独立准入链复核：诊断证据绝不提升为正式证据

- 复核类型：new-development / independent admission-pipeline review（只读）
- 仓库：`C:/Users/PC/Documents/odid编译/wksim`
- 基准：`main` HEAD `100ef1aafcc19c006d93eeb16b0c41e2352cdee6`（先复核）
- 复核期间 HEAD 移动：并发主会话提交 `34d6076/a9d9ccc/1a8d508` 使 HEAD 前进到 `1a8d5083b70461e6e6984566f7298c993f0c5392`。**所有被复核文件的 SHA256 前后逐字节一致**（见第 1 节），`f333316e…` 与 `100ef1a…` 在收尾 HEAD 上仍是祖先，故结论不变。
- 必需祖先：`f333316e6efa6b299b4288a9d91fb2bccedfb9d6`
  - `git merge-base --is-ancestor … HEAD` → exit `0`（是祖先）
- 复核对象：`33c2b06`（正式 `joint_profile` 对 `perf_switch_capture` 做 key-presence 拒绝）+ `100ef1a`（runner 接线实际 perf capture）
- 执行边界：纯 Python、只读检查；**未执行** native、构建、ROS/DDS、飞控 SITL、物理/模型、UE、MATLAB、任何进程启动
- 写入边界：仅本目录 `validation/coordination/codebuddy-perf-admission-review-20260913-01/`
- 交付后即停止写入；未改共享账本，未改任何既有文件

## 0. 结论（verdict）

**“诊断证据绝不提升为正式证据”的整条链在 HEAD `100ef1a` 成立。阻断项 0 个，非阻断项 5 个。**

正式 MIXED/PV 门 `joint_profile._mixed_proofs` 以**键存在**（`in`）拒绝 `perf_switch_capture`，对 `None/False/0/{}/[]/''` 等一切取值形态均拒绝，且发生在 `_raw_proof` 之前；runner 从不把 `strict_consumer_passed` 置真、也从不执行 strict consumer；额外 perf source 不破坏 source 集合身份；strict consumer 未运行/失败不会被误记为通过。所有结论仅基于纯 Python 与静态阅读，未做 native 运行。

## 1. 关键对象与稳定 SHA256（工作树与 HEAD blob 逐字节一致）

| 对象 | SHA256 | 角色 |
| --- | --- | --- |
| `Simulator/wksim_runtime/joint_profile.py` | `90cc868b8050b41e54ef0c38cf20104c58aefb97f07d1448dfd0be1f8633320a` | 正式门 |
| `tools/run_joint_flight.py` | `167a3c0790dde0bbef3b7bd2fee24616bdc623852aa7478a4c9356f425a670bf` | runner / marker / source 保留 / copytree |
| `tools/audit_mixed_control.py` | `f7f8816674f9526d48c808cfb10a31ca47fa7d08c6263ff531fb13edddb40234` | origin 审计 / `evidence_sha256` |
| `Simulator/wksim_runtime/perf_capture.py` | `c196616fe8324eed2d8b294ef52aaec1f982eb5330abbeb7ee17094399f32e0f` | 原生捕获适配器 |
| `Simulator/wksim_runtime/evidence.py` | `4f7f2e601ce3c2edfe54c1c48ed35d41133304c2b1fa56a969148c6ccbbfcb7a` | boot id / 证据格式化 |
| `validation/coordination/ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py` | `dee9a3b5c3cafb42e69836758ccaebd4dbd78e8fa569d203c7ca1d36a03179bc` | 独立 strict consumer |
| `validation/test_joint_profile.py` | `8afd1ae42d510282631e7fdd3f871a09987c25ecb97d3950fcec2a2c2b64cd05` | 纯测试 |
| `validation/test_mixed_profile_admission.py` | `2b2a6d9348528e360f51fd72d583c4faf0188f0d248737467d392cfc099febfe` | 纯测试 |
| `validation/test_run_joint_perf_capture.py` | `05ddf8638e804a87a1f4b32912c62237332e5ca16e63b39d420b26fe379d7ce0` | 纯测试 |

## 2. 阻断项

**无。** 见第 4 节逐条核验：正式门对 marker 的拒绝是键存在、先于原始证据遍历、且对任何取值生效；不存在“未运行/失败的 strict consumer 被记为通过”的路径。

## 3. 非阻断项

| 编号 | 事项 | 说明 | 最小修正建议 |
| --- | --- | --- | --- |
| N1 | 外部 decoded 结果的绑定靠“按值 + 操作前置” | runner 在 marker 里封存 raw/meta/windows 的 SHA 与期望输出名 `perf-decoded.json`；consumer 在 report 里回显输入 SHA。但没有任何**执行中的**代码把两者比对（`joint_profile.py:214-218` 只校验 audit 内封存的归档文件摘要）。因正式门整体拒绝 marker，不会导致提升，但 provenance 依赖人工比对。 | 在交付入口文档中写明比对步骤；或加一个纯 helper：`report.inputs.raw_sha256 != marker.outputs['raw']['sha256']` 即 fail-closed（不改共享账本）。 |
| N2 | `audit_mixed_control.py` 有意不标记 `perf_switch_capture` | 全文件 `grep -c perf` = 0；`retained_identity` 的 “Unexpected alternate workflow” 循环（`audit_mixed_control.py:132-134`）不含该键。因此 instrumented 归档仍可能拿到 flight audit `status='pass'`。这是刻意设计（原始审计要能复核 instrumented 飞行），正式性只由 `joint_profile._mixed_proofs` 单独保证；读者**不得**把原始审计 pass 当作正式 MIXED/PV 准入。 | 无需改码；如需，仅在审计报告 limitations 里点名诊断 marker。避免改动共享工具。 |
| N3 | consumer 的 `--windows` 可选，而 runner 总是封存 `perf-windows.json` | 不给 `--windows` 时 report `windows=null`。预期流程（带 `--windows` 且要求窗口交集非空）已文档化，但工具本身不强制。 | 保持现状；可选为交付脚本加“缺 windows 即调用方错误”的测试（不动 consumer）。 |
| N4 | `stream_completeness_proven` 源自被封存的元数据，而非独立原生复读 | `validate_kernel_loss_counter` 以 `read_ok=true / read_bytes=16 / errno=0 / count=0 / config.read_format=16` 判定完成性（`perf_stream_consumer.py:147-166`）。它是配置级完整性的断言，consumer 自身也以 `scope` 限定“configured event capture; not other tasks or physical accuracy”。 | 无需改码；让该 scope/limitations 随 decoded 证据一起保存。 |
| N5 | `strict_consumer_passed` 在本 runner 恒为 False | 有意为之：runner 只“为外部 consumer 封存”。读者若要分支，必须以 `perf_switch_capture` 键是否存在为准（正式门正是如此），不得看该布尔或只看原始审计状态。 | 无需改码。 |

## 4. 逐条核验

### C1 正式门拒绝时机与语义（`joint_profile.py:274-276`）
```
for marker in ('rate_timing_probe', 'group_work_timing', 'perf_switch_capture'):
    if marker in flight:
        raise ValueError('Formal mixed/PV evidence cannot include ' + marker)
```
- `in` 是**键存在**判定，与取值无关。
- 位置在 `flight/audit/admission` 被 `_pinned_json` 读出之后、`_raw_proof(pin, audit)`（`joint_profile.py:285`）**之前**；`_raw_proof` 在任何 marker 命中时都不会被调用。
- 独立探针以真实 `_mixed_proofs` + 真实 fixture 复现：`rejected_before_raw_proof` 通过。

### C2 取值形态全覆盖
独立探针 `chain_probe.py` 对 `None, False, True, {}, [], 0, '', 'enabled', {'diagnostic':'x'}` 逐一命中 `ValueError` 且消息含 `perf_switch_capture`；shipped 测试另覆盖 `True/False/None/{}`。结论一致。

### C3 runner 永不自证 strict consumer（`run_joint_flight.py:96-152, 468-477`）
- `start` 后 marker：`status='running', strict_consumer_passed=False`（`:92-93`）。
- 成功封印：`status='sealed_for_external_consumer', capture_lifecycle_complete=True, strict_consumer_passed=False`（`:143-146`）。
- 失败分支：`status='failed', capture_lifecycle_complete=False, strict_consumer_passed=False, error=…`，并置 `result['status']='failed'`（`:147-152`）。
- 静态检查：`tools/run_joint_flight.py` 中不存在字符串 `strict_consumer_passed=True`。

### C4 runner 不执行 consumer
`perf_stream_consumer` 只作为 source 身份（`PERF_CAPTURE_SOURCES[-1]`、`digest(REPO/consumer)`、`PERF_CAPTURE_SOURCES` 加入 `sources`）出现，没有任何 `Popen/subprocess` 指向它。因此不存在“consumer 未跑却由 runner 记为通过”的路径。

### C5 捕获失败即飞行失败
`finalize_perf_capture` 的 `except BaseException` 把 `result['status']` 改为 `failed` 并写 `error`；随后 copytree 归档。正式门以 `flight['status'] != 'pass'`（`:278`）拒绝。shipped 三条 fail-closed 测试（stop 异常、缺完整 rate 段、库在运行中被改、窗口越界）全通过。

### C6 额外 perf source 不破坏 source 集合身份
- 正式门（`joint_profile.py:329-339`）：`required <= sources.keys()`（子集）+ 对 `sources` 每一项要求 audit 内有对应 `source__…txt` 且摘要一致，随后 `_raw_proof` 校验归档内每个 `evidence_sha256` 文件。
- 飞行审计（`audit_mixed_control.py:135-146`）：`source__*` 文件集合与 `result['source_sha256']` 键集合**完全相等**。
- runner 在 `perf_request` 非空时把 `PERF_CAPTURE_SOURCES`（5 个文件）加入 `sources`（`:509-510`），并为每项写 `source__*.txt`（`:523-525`）；两侧集合由 `result['source_sha256']` 推导，保持自洽。
- 独立探针：把 5 个 perf source 追加进 fixture 后真实 `_mixed_proofs` 仍接受；同一批额外 source 无法夹带 marker 通过（两个用例均通过）。

### C7 marker 只可能落在 MIXED profile（正式门拒绝的那一个）
`perf_capture_request`（`:73-82`）与 CLI parser（`:1246-1250`）双重要求 `task_profile == MIXED_PROFILE`；否则不建 marker、不加入 perf source。

### C8 result/source 保留与 copytree
- marker 在 `:471-477` 建立，含 `classification='diagnostic_only'`、`formal_evidence=False`。
- `:523-525` 写 `result['source_sha256']` 与 `live/source__*.txt`。
- `finally` 中 `finalize_perf_capture`（`:1100-1101`）把 raw/meta/windows 写进 `live`。
- `save(live/'result.json')`（`:1150`）后 `shutil.copytree(live, archive, dirs_exist_ok=True)`（`:1151`）；`source_unchanged` 在 `:1114` 复算（含 perf source）。

### C9 原始审计 `evidence_sha256` 与 `_raw_proof`
`audit_mixed_control.py:822` 取 root 下**所有文件**摘要；`joint_profile._raw_proof`（`:210-218`）要求 `evidence_sha256` 非空且逐项与磁盘一致，路径必须在 root 内。若 consumer 在原始审计**之前**运行并把 `perf-decoded.json` 放进 archive，它会被一并封存；反过来则不封存。该先后关系是操作约束（见 N1）。

### C10 strict consumer 约束（实测 12/12 + shipped 84/84）
| 约束 | 行为 | 证据 |
| --- | --- | --- |
| `--require-kernel-counter` 缺失计数 | 退出 3，`kernel_loss_counter_required`，**不**写输出（fail-closed） | 探针 `legacy_rejected_when_required`, `rejected_legacy_wrote_no_output` |
| 计数为零 | 退出 0，`stream_completeness_proven=true` | `zero_counter_proves_completeness` |
| 计数非零 | 退出 3，`kernel_loss_counter_nonzero` | `nonzero_counter_rejected` |
| `--output` 已存在 | 退出 3，`output_exists_refusing_overwrite` | `refuses_to_overwrite_output` |
| `--windows` 省略 | 合法，report `windows=null` | `windows_absent_is_null` |
| `--windows` 在内层区间 | 退出 0，输出整数纳秒交集 | `windows_optional_and_intersected` |
| `--windows` 越出内层区间 | 退出 3，`windows_outside_capture_bounds` | `windows_outside_inner_rejected` |
| 不自证 Full | `classification='diagnostic_only'`, `full_acceptance=false`, `flight_conclusion=null` | `legacy_no_self_full` |

### C11 绑定但不自证 Full
绑定：marker 记录期望输出名与 consumer 源 SHA（`:474-476`）；marker 记录 raw/meta/windows 的字节数与 SHA（`:139-142`）；consumer report 回显 `inputs.*_sha256`（`perf_stream_consumer.py:524-530`）；审计可封存 decoded 文件（C9）。
不自证：consumer report 明示 `diagnostic_only` / `full_acceptance=false`；runner marker 明示 `formal_evidence=False`；正式门整体拒绝。**注意 N1**：绑定未被执行中代码强制比对。

## 5. 测试与探针结果

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 三模块 pytest | `python -m pytest validation/test_joint_profile.py validation/test_mixed_profile_admission.py validation/test_run_joint_perf_capture.py -q` | 38 passed, 1 failed, 49 subtests passed |
| perf/marker 定向 | 同上 `-k 'perf or marker or mixed_result or strict or reject or seal or lifecycle'` | 26 passed |
| shipped consumer 套件 | `python -B validation/coordination/ds-perf-stream-consumer-20260913-01/test_perf_stream_consumer.py` | 84 checks, 0 failed |
| 独立链路探针 | `python -B test-outputs/chain_probe.py` | 16 cases, 0 failures |
| 独立 consumer 约束探针 | `python -B test-outputs/consumer_constraints_probe.py` | 12 cases, 0 failures |

**唯一失败**：`validation/test_joint_profile.py::JointProfileTests::test_source_file_tamper_and_escape`，原因 `OSError WinError 1314`——本机 Windows 缺少创建符号链接的特权，失败点在 `path.symlink_to(outside)`，与准入链无关；在允许 symlink 的 Linux/WSL 上预期通过。分类：环境性、非阻断。

## 6. 交付物

- `review.md`（本文件）
- `review.json`（机器可读结论、稳定 SHA、逐条 check）
- `.gitattributes`（`* -text`）
- `test-outputs/pytest-three-modules.txt`
- `test-outputs/consumer-suite.txt`
- `test-outputs/chain_probe.py` / `chain_probe.json`
- `test-outputs/consumer_constraints_probe.py` / `consumer_constraints.json`

## 7. 停止声明

本目录写入在以上文件完成后**停止**。未修改任何既有文件，未改共享账本，未执行 native/构建/ROS/飞控/模型/UE/MATLAB，未做任何进程启动或清理。
