# 计划 59：G6 T2 时间字段结构独立核对（2026-09-14）

## 1. 目的与边界

本切片在共享 wksim 仓库内新增一个**独立离线**的 T2 结构核对器，用于重算已封存 501 行
major 证据中三个 `schedule_metadata` 时间槽的两种写法：

- **乘积形式** `(k * 0.001) * gain`（native major 根输出所记录的时钟写法）；
- **除法形式** `(k / 1000) * gain`（native 驱动 `input_time_s` 所记录的写法）。

核对器不复用 `validation/coordination/major-time-acceptance-20260913-01/verify_times.py`
的任何输出：它自行从 tracked 合同重新推导槽位/单位/整型宽度，自行按 little-endian
binary64 行重新解码 split 参考数组，再逐行做 packed binary64 位精确比较。

证据分级是本切片的硬要求：这里只处理**调度证据**（时间字段的写法与行计数）。
动力学与物理预算（三个数组其余 118 个非时间槽、任何绝对/相对误差预算、任何
物理量精度）既未评估、也未批准、更未界定。

本切片不关闭任何事项：`r1_status` 仍为 `numerical_failed`，`#84` / `G6` / `Full`
保持 open，`budget_approved=false`、`g6_acceptance=false`、`physical_accuracy=false`，
且不构成 #83 重跑、不触发任何 MATLAB/Simulink/native/ROS/DDS/SITL/flight/UE 执行。

## 2. 依赖与 tracked 状态（第一步核验）

**溯源锚点（先于一切产物）**：核对器把溯源绑定到稳定证据锚点
`f333316e6efa6b299b4288a9d91fb2bccedfb9d6`（见 `AGENTS.md`），绝不绑定到某个精确 HEAD。
观测到的 HEAD 仅作为运行期观测值读取，用于证明两点：(a) 它自锚点派生
（`git merge-base --is-ancestor <anchor> <观测 HEAD>`，退出码 0）；(b) 对每个被钉住的证据
路径，`git diff <anchor>..<观测 HEAD>` 为空（字节逐路径一致）。观测 HEAD 的具体取值**从不**
写入文档，也不在源中内嵌任何精确 HEAD，因此核对器对 HEAD 在锚点的任何干净后代之间漂移
都保持正确。非后代检出、任一被钉住路径在锚点..HEAD 间发生变化（pinned-path overlap）、
或探针不可用，均 fail closed（`status="blocked"`）且不写入结果文档。

核对器在生成任何产物之前，先核验每个证据依赖是否存在于 `HEAD` 树，且磁盘字节与声明
的 SHA256/size 一致；不一致即 fail closed，并记录精确的缺失输入。

| 依赖 | 角色 | HEAD 跟踪 | SHA256 | size |
| --- | --- | --- | --- | --- |
| `validation/e0-major-recorder-parent-final-01/record.jsonl` | 已封存 major 运行 | 是 | `8ce61b33…ff354` | 936395 |
| `Simulator/wksim_core/numerical-conformance-v1.json` | 冻结合同 | 是 | `23d72e26…2c08f0` | 29846 |
| `validation/coordination/major-time-acceptance-20260913-01/verification.json` | 伴随核验记录 | 是 | `edf6a755…fcd6f70` | 2417 |
| `validation/coordination/major-time-acceptance-20260913-01/initial-assumption-rejected.json` | 被拒假设记录 | 是 | `d8965410…53a9a6` | 300 |
| `validation/coordination/major-time-acceptance-20260913-01/verify_times.py` | 既有读者 | 是 | `01c14682…efdc030` | 3261 |
| `docs/2026-09-13-major-time-conventions.md` | 时间约定说明 | 是 | 构建时记录 | — |

**未跟踪的原始输入（必须显式声明，绝不冒充 tracked 证据）**：三个 split 参考数组位于
`validation/numerical-conformance-u56ce17a/C0/`，该目录被 `.gitignore` 的
`/validation/*/` 规则覆盖，因此在 HEAD 中不存在。核对器把它们声明为
`tracked_at_head=false` 的原始输入，按 SHA256/size 绑定，并在缺失或漂移时 fail closed：

| 原始输入 | SHA256 | size | 行宽 |
| --- | --- | --- | --- |
| `…-u56ce17a/C0/Vehicle60.f64` | `fcbfb343…ebc8ceb` | 244488 | 61 |
| `…-u56ce17a/C0/Sensor30.f64` | `066a5561…45e8b90` | 124248 | 31 |
| `…-u56ce17a/C0/GPS30.f64` | `459dd65a…45cc4074` | 124248 | 31 |

若这些原始文件缺失，核对器输出 `status="blocked"` 且**不写入任何结果文档**，只在
`missing_inputs` 中逐项列出精确路径、期望 SHA256 与期望 size；不猜测、不填充、不省略。

## 3. 复算结果（仅调度证据）

三个 `schedule_metadata` 时间槽由合同推导得出（`array_element_count` 亦由合同
observable 的最大索引重算，而非手写常量）：

| 槽 | 单位 | gain | 合同来源 | 乘积形式匹配 | 与除法形式不同的行数 |
| --- | --- | --- | --- | --- | --- |
| `Vehicle60[2]` | s | 1 | `cpp:3917,7822` | 501/501 | 72 |
| `Sensor30[0]` | us | 1e6 | `cpp:3922,7437` | 501/501 | 61 |
| `GPS30[0]` | us | 1e6 | `cpp:3922,7727` | 501/501 | 61 |

参考数组保留的前导时间列是**未缩放的秒时钟**（`unit="s"`、`gain_applied_to_clock=1`），
对三份文件均满足：乘积形式 501/501、除法形式 429/501。**501/501 与 429/501 只有在
本次独立重算仍然支持时才保留**，文档中的 `reported_counts_supported` 逐项记录该结论。
与除法形式不同的行索引同时写入文档（`measured_division_mismatch_indices`），例如
`Vehicle60[2]` 的前几行为 9, 13, 18, 26, 36, 43, 51, 52, 59, 71, 72, 86, 87, …。

产物同时区分两件容易被混淆的调度证据：major 根输出的时间列使用乘积形式（501/501），
而 native 驱动 `input_time_s` 使用除法形式（其对乘积形式差异行数为 72）。
这不是物理误差，只是 binary64 运算顺序差异。

负向控制：把第 17 行错加一个采样步后，三个时间槽都只在该行被拒（
`shifted_row_check.only_shifted_row_rejected=true`）。

## 4. 产物

| 文件 | 说明 |
| --- | --- |
| `tools/check_g6_time_field_forms.py` | 独立结构核对器（只读、确定性序列化、fail-closed 校验器） |
| `validation/g6-time-field-forms-20260914.json` | 确定性结果文档（schema `wksim.59-g6-time-field-forms.v1`） |
| `validation/test_check_g6_time_field_forms.py` | 离线测试（确定性、source pin/tracked HEAD、计数复算、负向突变、无预算/批准/收口、R1 `numerical_failed` 与 #84/G6/Full open） |
| `docs/plan/59-g6-time-field-forms-20260914.md` | 本计划 |

文档 schema 顶层键（固定顺序）：
`schema, kind, version, date, issue, title, work_class, layer, authority, effective,
generator, generator_command, base_ancestor, status, block_reason_codes,
r1_status, g6_acceptance, physical_accuracy, issues_closed, budget_approved,
pending_approvals, open_items, identity, evidence_dependencies, form_under_test,
contract_time_slots, recomputed, evidence_class_split, untracked_inputs,
missing_inputs, blockers, reproduce, nonclaims, scope_limits`。

`recomputed.streams[*]` 逐流记录：槽位、单位、gain、`semantic_class="scheduling_evidence"`、
行数、整型宽度校验、乘积/除法形式匹配行数与不匹配索引、形式分歧行数、位移负向控制、
以及列的 packed binary64 SHA256。`recomputed.reference[*]` 记录三份参考数组的行数、
行宽、前导时间列位置与单位、两种形式的匹配行数、以及非时间列的全匹配盘点。
所有哈希/size/路径均出现在文档中，便于任何人用同一批字节复现。

## 5. 验证

1. `python -B tools/check_g6_time_field_forms.py --repo-root .` 生成文档；
2. `python -B tools/check_g6_time_field_forms.py --repo-root . --validate` 返回 `ok=true`；
3. `python -B -m unittest validation.test_check_g6_time_field_forms` 在普通工作树模式通过；
4. 同一测试套件在仓库外临时 `GIT_INDEX_FILE` 下、仅精确 force-add 上述四个候选文件
   （exact4）后再次通过：候选文件的 staged blob 与工作树字节一致，且 tracked 证据仍从
   HEAD 读取，文档字节不变。

测试覆盖：确定性（重复构建字节一致）、source pin 与 tracked HEAD、计数复算
（501/501、429/501、72/61/61、位移拒绝）、负向突变（结构、schema、依赖性、未跟踪输入、
验收/收口翻转、复算字段篡改）、缺失输入 fail-closed、以及无预算/批准/收口声明。
溯源锚点负向测试：非后代检出（对锚点父提交做实弹 `merge-base` 检测，断言
`base_ancestor_not_ancestor` 块）与 pinned-path overlap（在一次性双提交沙箱中改动某被钉住
路径，断言 `pinned_path_overlap` 块；未改动路径与相同端点均不产生该块）。文档断言观测 HEAD
取值从不落盘，且不存在任何精确 `head` 键。
测试对真实 git 索引与 HEAD 只读：不 staging、不 commit、不 push，也不修改任何既有
证据、合同或 trace 字节。

## 6. 非主张

- 非数值验收：未运行任何模型、可执行体或求解器，只重新解码已封存字节；
- 非物理精度主张：本切片只涉及调度时间字段，动力学与物理预算未评估、未界定、未批准；
- 不批准误差预算，不请求任何批准，不冻结任何合同；
- 不关闭 `#84` / `G6` / `Full`，`r1_status` 保持 `numerical_failed`；
- 除法形式差异不表示记录错误，只是 binary64 运算顺序差异；
- 参考身份仍来自冻结合同的 SLX 11.8 normal，而不是从旧 R1 目录名推断。
