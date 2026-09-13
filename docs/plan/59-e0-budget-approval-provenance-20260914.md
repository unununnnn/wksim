# #59 G6/B1 预算批准溯源台账（fail-closed，零批准）

2026-09-14。本文与机器可读台账 `validation/e0-budget-approval-provenance-20260914.json` 及离线自测 `validation/test_e0_budget_approval_provenance.py` 成对交付。CodeBuddy 未完成稿中的临时生成器已删除；独立复核产物写在 `validation/coordination/deepseek-g6-budget-provenance-review-20260914-01/**`（修复前 FAIL 证据，保持原样不再改动），本次修复的产物写在 `validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/**`。两者都位于协调目录类之下，因而**在结构上不可作为** owner 或 derivation 记录（见下文外部记录位置规则）；它们只作为溯源被如实记名。

本切片只做**台账与闸门**：枚举冻结的 120 个 e0 输出槽，为每个槽记录预算升级所需的全部字段，并把当前状态钉死为“无预算、无批准”。它**不是**批准行为，也不提供任何通过编辑台账即可获得的批准通道。

## 身份与边界

| 项 | 值 |
| --- | --- |
| 工作类别 | new-development / offline provenance ledger（无验收运行） |
| cwd / 分支 | `C:\Users\PC\Documents\odid编译\wksim` / `main` |
| 来源钉 / 基线 HEAD | `6eafdf9c0b734db07a9fe790c86b409d3468c10b`（祖先/来源钉，不要求提交后当前 HEAD 相等） |
| 基线祖先 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0 |
| 独占写入 | 本文、`validation/e0-budget-approval-provenance-20260914.json`、`validation/test_e0_budget_approval_provenance.py`、`validation/coordination/cursor-g6-budget-related-source-p2-repair-20260914-01/**`。冻结只读、本切片不得改写：`deepseek-g6-budget-provenance-review-20260914-01/**`、`deepseek-g6-budget-provenance-repair-20260914-01/**`、`cursor-g6-budget-postrepair-review-20260914-01/**`、`deepseek-g6-budget-provenance-repair2-20260914-01/**`、`cursor-g6-budget-c1-takeover-20260914-01/**`、`cursor-g6-budget-frame-sequence-repair-20260914-01/**`、`cursor-g6-budget-frame-final-review-20260914-01/**`；三份 frame 候选、G1/G3/Full 与历史回执不得改写 |
| 未启动 | native / 模型 / MATLAB / ROS / 飞控 / UE / 构建 / 飞行 / #83 |
| 未变更 | 未 `git add/commit/push`，未改 GitHub，未编辑任何既有文件 |

提交后语义：上表 `6eafdf9c0b734db07a9fe790c86b409d3468c10b` 是祖先/来源钉，只要求 `git merge-base --is-ancestor` 对该钉与当前 HEAD 为 0，不要求提交后 HEAD 仍等于该钉。三份切片文件提交后，台账允许且应当成为 HEAD blob；若 `git show HEAD:` 台账路径存在，其字节与 SHA-256 必须与工作树以及本文/台账中已记录的冻结钉一致。已记名的 `validation/coordination/*-20260914-01` 复核/修复目录只作为溯源（核对名称与已记录来源），不是干净检出的磁盘运行时依赖；它们仍属于 coordination 位置类，C1 owner gate 不得因此弱化。`related_artifacts` 的未跟踪事实只绑在该来源钉上：`tracked_at_source_head=false`，并用 `git show` / `ls-tree` 核对该钉；不得要求未来当前 HEAD 永远未跟踪。后续把某条 related 路径跟踪进当前 HEAD，也不得自动把它提升为 pin、owner 或 derivation。每条 related 的 `id→path→sha256` 三元组由测试模块内常量独立冻结，`validate()` 做精确比较：路径拼写（含反斜杠、`./`）、哈希、顺序、重复 id/path、额外或缺失记录一律以 `related_artifact_mismatch` 失败关闭，不会把 related 晋升为 evidence pin。陈旧 frame 精确路径/陈旧哈希 `33c490…` 仍额外拒绝。`SOURCE_HEAD` 缺失或不为当前 HEAD 祖先时，`validate(check_git=True)` 本身返回稳定拒绝码 `source_head_missing_or_not_ancestor`，不依赖外层 unittest；`git show` 与 `ls-tree` 不一致仍失败关闭。`check_git=False` 只走结构路径：三元组、声明键与位置类仍可测，但不探测 SOURCE_HEAD 对象或祖先。独立的 frame/datum 终稿不再写入 related_artifacts：旧记录把 `validation/e0-frame-datum-binding-20260914.json` 写成哈希 `33c490…`，而当前终稿是 `5d589075…`，路径/哈希会误导。

## 冻结输入（全部取自 HEAD blob）

钉值字节一律来自 `git show HEAD:<path>`，不读工作树副本；未跟踪、仅暂存、被替换或与 HEAD 有 `git diff HEAD` 漂移的路径一律拒绝。钉值 `id → path` 映射与 120 槽集合在测试模块内独立冻结，台账必须与之一致。

| 钉 id | 路径 |
| --- | --- |
| r1_contract | `Simulator/wksim_core/numerical-conformance-v1.json` |
| slot_manifest | `validation/e0-source-to-slot-manifest-20260911.json` |
| rhs_references | `validation/e0-current-rhs-references-20260912.json` |
| current_source_mapping | `validation/e0-current-source-mapping-20260912.json` |
| budget_manifest_schema | `docs/plan/10-g6-budget-manifest.schema.json` |
| g6_remediation_contract | `docs/plan/10-g6-remediation-contract.md` |
| dynamic_budget_source_map | `docs/plan/59-e0-dynamic-budget-source-map.md` |
| same_source_command | `docs/plan/59-e0-same-source-command.md` |
| same_source_entry | `tools/run_e0_same_source_conformance.py` |
| budget_manifest_generator | `tools/generate_g6_budget_manifest.py` |
| budget_manifest_validator | `tools/validate_g6_budget_manifest.py` |
| solve_form_decision | `validation/e0-g6-solve-form-decision-20260914.json` |
| budget_evidence_audit | `validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json` |

`related_artifacts` 记录启发本切片、但在来源钉 `6eafdf9c0b734db07a9fe790c86b409d3468c10b` 上未跟踪的产物（2026-09-14 B1/B4 前沿审计三份交付物）。它们**没有钉 id**，测试内常量冻结每条 `id→path→sha256` 三元组并由 `validate()` 精确比较，断言 `tracked_at_source_head=false`，并对该来源钉做 `git show` / `ls-tree`；不得占用任何钉 id，也不得要求未来当前 HEAD 永远未跟踪。把它们提升为钉值、owner 或 derivation 会被拒绝。在飞 frame/datum 补充件已从该列表移除，避免陈旧哈希 `33c490…` 与当前终稿 `5d589075…` 互相误导。

## 槽集合与划分

- 总计 **120** 槽（Vehicle60 60 + Sensor30 30 + GPS30 30），与冻结 R1 合同的 32 个 observable 完全对应。
- **56 个 dynamic candidate**：出现在 `rhs_references` 槽集合中的槽（53 个语义量 + 3 个时间字段；RHS 解析状态 26 terminal / 2 local_bound / 28 unresolved）。
- **64 个 policy slot**：其余槽，按其 R1 `semantic_status` 分为 **5 个 interface_metadata**（`Vehicle60[0..1]`、`Sensor30[14]`、`GPS30[11..12]`）与 **59 个 reserved_not_physical_coverage**。

## 每槽字段

| 字段块 | 内容 | 当前值 |
| --- | --- | --- |
| `source_identity` | R1 observable id、native unit 及其来源、已提交源码映射（outport、11.8 行范围、RHS 解析状态与原因、slot manifest 状态）、证据类别 | 已提交可派生；56 槽中 28 槽 RHS 未闭合记为 `committed_partial` |
| `metric` | 冻结 metric 标识符、是否需要等价类处理、对应 owner 决策、状态 | `abs_le_a_plus_r_absref_with_rms_cap_v1`；姿态与 course 槽需要 D-03 |
| `domain` | 已激励响应清单引用、声明适用域、证据类别 | 清单指向 `pin:r1_contract#cases`；`declared_domain` 为 null（mixed：清单已提交，适用域属 owner） |
| `frame_datum` | frame、datum、状态、证据类别、owner 决策 | 全 null；dynamic 槽 `owner_only`（D-12），policy 槽 `not_applicable`（D-01） |
| `derivation` | 是否必需、外部溯源引用、推导类别、状态、证据类别、命中的禁止类别 | `ref=null`、`derivation_class=null`、`status=blocked` |
| `budgets` | `abs_budget`、`rel_budget`、`rms_budget`、状态 | 全部 null，`status=blocked` |
| `approval` | `state`、`decision_id`、`approver`、`decided_utc`、`decision_text_digest`、`decision_ref`、`external_record_pinned`、证据类别 | `not_made`，全部身份字段 null，`external_record_pinned=false` |
| `status` | `blocked`（56 dynamic）或 `pending_owner_policy`（64 policy） | 见上 |
| `owner_inputs` | 解除该槽所需的 owner 决策块 | D-01…D-12 子集 |

**已提交可派生 vs owner-only**：`source_identity`（R1 身份、native unit、11.8 行范围、RHS 状态）与 `metric` 的冻结标识符、时间网格/采样相位属于已提交可派生；`derivation`、`domain` 的声明适用域、`frame`/`datum`、`budgets` 三元组与全部 `approval` 字段属于 owner-only。`external_owner_records` 与 `external_derivation_records` 当前均为空列表。

## 必须拒绝的溯源类别与漏洞规则

台账把 RD-01..RD-12 声明为禁止溯源类别（每类含标记词、理由与依据），把 L1..L4 声明为漏洞规则；**执行用的标记词表与规则 id 集合冻结在测试模块内**，因此台账删除某条规则仍会失败关闭：

- RD-01 R1 观测差值；RD-02 候选/同源观测差值；RD-03 由 ULP 反推预算；RD-04 阶数/网格收敛/epsilon 推断；RD-05 噪声幅值/增益/参数/教材推断；RD-06 自指证据；RD-07 占位串；RD-08 SITL 门槛当预算；RD-09 未跟踪在飞证据；RD-10 `aligned`/0 ULP 当结论；RD-11 合成排序探针；RD-12 把 reserved 计为物理覆盖。
- L1 裸 `approval='approved'`；L2 自由文本 derivation/domain；L3 自由文本 frame/datum；L4 自指 `contract_sha256`。

L2/L3 的执行不依赖标记词拼写：`derivation.ref`/`derivation_class`/`domain.declared_domain` 只要非 null，就必须由 `derivation.ref` 指向一个钉定的外部 derivation 记录；`frame_datum.frame`/`datum` 只要非 null，就必须由 `approval.decision_ref` 指向一个钉定的外部 owner 记录且 `external_record_pinned=true`。标记词扫描只是额外一层，因此 `RD-01` 这样的类别 id 或 `ENU`/`WGS84` 这样的可信拼写都无法绕过。

扫描范围为溯源承载字段（`derivation.ref`/`derivation_class`/`forbidden_class`、`domain.declared_domain`、`frame_datum.frame`/`datum`、`approval.decision_id`/`decision_ref`/`approver`），避免误伤合法词表（例如 `partition=dynamic_candidate`）。

## 未来升级所需的外部 owner 记录（不代造）

槽位离开 `blocked` / `pending_owner_policy` 需同时满足：

1. `decision_ref` 指向 `external_owner_records` 中的 id，且该记录**在 HEAD 被跟踪**并带有钉定的 `path` 与 `sha256`；
2. `derivation.ref` 指向 `external_derivation_records` 中的 id，且该记录同样被钉定并跟踪于 HEAD；
3. owner 记录含 `approver`、`decided_utc` 与决策文本，文本 sha256 等于 `decision_text_digest`；
4. owner 记录逐槽写明被升级的 `slot_id` 与精确的 abs/rel/rms 三元组，并由 project owner 或 D-07 指定的被授权人签署；
5. 外部记录位于本切片包之外：不得是台账、本文或测试文件，也不得是任何 `validation/coordination/**` 路径（任意深度、任意目录名），并须为仓库相对路径（不得绝对路径、盘符或 `..` 穿越）。该位置规则按**路径类**实施，不硬编码任何目录名，且**所有路径段比较在斜杠归一与点段处理之后一律 Unicode `casefold`（不是 ASCII-only `lower`）**：`validation/COORDINATION/**`、`validation/Coordination/**`、`VALIDATION\\Coordination\\**`、点段与反斜杠、段尾点/空格（Windows 等价折叠）与 `validation/coordination/**` 同类，在 Windows 与 Linux 上同样拒绝，`check_git=False` 即可见拒绝；只有**整段相等**才算命中，因此 `coordinationish`、`my-coordination`、`coordination-notes` 等更长段仍属不同类别。冻结输入钉值与升级记录是不同类别：`validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json` 继续作为合法钉值（按 id/path/sha256 与 HEAD 校验，钉值路径仍按冻结拼写**精确**比较），但在同一路径上永远不能成为 owner/derivation 记录（拒绝码 `external_record_location_violation`）；
6. `budget_approved`、`g6_acceptance`、`physical_accuracy`、`issues_closed`、`effective` 仍为 false，`r1_status` 仍为 `numerical_failed`。

由于 `external_owner_records` 与 `external_derivation_records` 当前为空，**任何批准声明（包括把台账自身填满）都会被拒绝**：这是“编辑台账不能产生批准通道”的可执行形式。

## 失败边界

未知/缺失顶层键、未知/缺失槽键、**子块（`source_identity`/`metric`/`domain`/`frame_datum`/`derivation`/`budgets`/`approval`）未知或缺失子键**、`required_subfields`/`required_slot_fields` 与冻结闭集不符、槽重复、槽集合不符、槽数非 120、划分不符、policy 槽被丢弃或自动批准、状态越出词表、**子块状态越出词表（`budgets`/`metric`/`domain`/`derivation` 只能为 `blocked`，`frame_datum.status` 必须跟随槽状态）**、出现数值预算、非有限或负数、出现批准身份、无外部记录的批准声明、无外部记录的 derivation/domain/derivation_class（L2）、无外部 owner 记录的 frame/datum（L3）、**外部 owner/derivation 记录位置不合法（`external_record_location_violation`：任何 `validation/coordination/**` 路径、本切片包文件、绝对路径或 `..` 穿越；路径段比较在斜杠归一与点段处理后 Unicode `casefold`，故 `COORDINATION`/`Coordination`/反斜杠/点段/段尾点空格等拼写同类命中）**、命中禁止溯源类别、占位值、自指证据、钉值缺失/被替换/未跟踪/漂移/哈希不符、**related 三元组与冻结常量不符（`related_artifact_mismatch`：路径拼写、哈希、顺序、重复 id/path、额外或缺失记录）**、**`SOURCE_HEAD` 缺失或不是当前 HEAD 祖先（`source_head_missing_or_not_ancestor`，仅 `check_git=True`）**、接受标志为真、`r1_status` 改动、**`slot_set` 与 slot 列表不符**、**counts 键集合或数值与实测不符（含 `dynamic_rhs_resolution` 与 frame/datum 绑定计数）** —— 一律拒绝。

## 独立复核与修复（2026-09-14）

- 修复前独立敌意复核（DeepSeek，8 份产物）位于 `validation/coordination/deepseek-g6-budget-provenance-review-20260914-01/**`，判定 **FAIL**：原始台账、13 个钉值与 120 槽推导本身全部通过，失败在**执行面**——`validate(ledger, check_git=False)` 放行了 58 个敌意变异中的 15 个（**14 个 fail-open** + 1 个故意放行的 benign 重排；仅正确拒绝 43 个），并有 1 处悬空的复核目录引用。该目录自修复开始起冻结只读，作为修复前证据保留。
- 第一轮修复产物位于 `validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/**`，含 findings 逐条修复映射、修复后候选上的独立变异探针结果（Windows 与 Ubuntu-22.04 各一份）与**修复前后逃逸对照表**。
- 第一轮修复内容：L2/L3 由“标记词扫描”升级为“必须有钉定外部记录”；七个子块改为闭集键 + 子块状态词表；`slot_set` 与 counts 全面交叉核对；外部记录位置改为结构化路径类规则，并删除悬空目录引用、如实记名真实复核与修复目录。修复后同一 58 项变异电池中 14 个原 fail-open 全部被拒绝（唯一仍放行的仍是故意 benign 的 `M03-slot-reorder`）；两平台结果一致。
- 修复后独立敌意复核（Cursor，9 份产物）位于 `validation/coordination/cursor-g6-budget-postrepair-review-20260914-01/**`，判定 **FAIL**：七项原 findings 及其 14 个逃逸全部关闭，但它用 53 项电池发现 **C1**——位置规则按段比较时**未折叠大小写**，因此 `validation/COORDINATION/**` 与 `validation/Coordination/**` 被放行（3 项逃逸：B07/B08/B16）。该目录同样冻结只读。
- 第二轮修复（C1）产物位于 `validation/coordination/deepseek-g6-budget-provenance-repair2-20260914-01/**`：候选侧已写入 Unicode/`casefold` 路径段比较（含段尾点/空格按 Windows 等价折叠），并留下探针结果、套件日志、`review.md`/`findings.json`/`self-check.json`。该目录**在收据生成中途失败**，没有 `receipt.md` / `receipt.json` / `SHA256SUMS`；本切片只读核对其现有字节，不覆盖、不补写。
- C1 接管续派产物位于 `validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/**`：在保留上述正确候选工作的前提下补 Unicode casefold 回归，独立重跑冻结电池与完整专用套件（Windows 与干净 Ubuntu-22.04），并写出带明确 PASS/FAIL 的 `receipt.md`、`review.md`、机器可读结果与 `SHA256SUMS`。这不是 owner 批准，也不关闭 #59/#10/G6/Full。
- Budget/Frame 交叉提交语义修复产物位于 `validation/coordination/cursor-g6-budget-frame-sequence-repair-20260914-01/**`：related_artifacts 的未跟踪事实改绑来源钉，移除陈旧 frame artifact 记录，并在临时仓用 Budget→Frame 与 Frame→Budget 两种顺序验证。这不是 owner 批准，也不关闭 #59/#10/G6/Full。
- 交叉提交独立终审位于 `validation/coordination/cursor-g6-budget-frame-final-review-20260914-01/**`（只读）：P1 关闭，但留下 P2——`validate()` 只冻 related id，反斜杠/`./` 加当前 frame 哈希可逃过陈旧 frame 精确路径比较；`SOURCE_HEAD` 缺失时 `validate()` 本身不拒，只靠外层 unittest。该目录冻结只读。
- related/SOURCE_HEAD P2 修复产物位于 `validation/coordination/cursor-g6-budget-related-source-p2-repair-20260914-01/**`：把 related 三元组全部交给测试常量精确比较，并让 `validate(check_git=True)` 对缺失/非祖先 SOURCE_HEAD 返回稳定拒绝码。这不是 owner 批准，也不关闭 #59/#10/G6/Full。
- 台账状态始终保守：120 槽、0 数值预算、0 批准身份、0 外部记录、全部验收标志为 false、`r1_status=numerical_failed`。

## 验证

```powershell
python -B -m unittest validation.test_e0_budget_approval_provenance
python -B -m unittest validation.test_g6_budget_manifest
python -B -m unittest validation.test_e0_same_source_conformance
python -B -m unittest validation.test_e0_source_to_slot_manifest
```

```bash
python3 -B -m unittest validation.test_e0_budget_approval_provenance
python3 -B -m unittest validation.test_g6_budget_manifest
python3 -B -m unittest validation.test_e0_same_source_conformance
python3 -B -m unittest validation.test_e0_source_to_slot_manifest
```

修复后的独立变异探针（离线、不启动任何原生/模型/MATLAB/ROS/飞控/UE/构建过程，也不改动 git）：

```powershell
python -B validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/probe.py `
  --root . `
  --git-evidence validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/git-evidence.json `
  --before validation/coordination/deepseek-g6-budget-provenance-review-20260914-01/results-windows.json `
  --tag windows `
  --out validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/results-windows.json
```

```bash
python3 -B validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/probe.py \
  --root . \
  --git-evidence validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/git-evidence.json \
  --before validation/coordination/deepseek-g6-budget-provenance-review-20260914-01/results-linux-ubuntu-22.04.json \
  --tag linux-ubuntu-22.04 \
  --out validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01/results-linux-ubuntu-22.04.json
```

第二轮修复后的 C1 复验探针（同一 53 项冻结电池，从 Cursor 复核探针导入，离线、不改动 git）：

接管切片独立复验（导入 Cursor 冻结 53 项电池，不执行、不改写该探针；离线、不改动 git）：

```powershell
python -B validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/probe.py `
  --root . `
  --git-evidence validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/git-evidence.json `
  --tag windows `
  --out validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/results-windows.json
```

```bash
python3 -B validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/probe.py \
  --root . \
  --git-evidence validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/git-evidence.json \
  --tag linux-ubuntu-22.04 \
  --out validation/coordination/cursor-g6-budget-c1-takeover-20260914-01/results-linux-ubuntu-22.04.json
```

三份交付物均为 LF 归一（测试断言不含 CR）。

## 非声称

本台账不发明任何预算数值、derivation、domain、frame、datum 或批准；不批准 G6、不冻结同源合同、不关闭 #59/#10/G6/Full；不改判 R1 `numerical_failed` 及其保留失败；不从任何追迹、测试或阻塞理由集合推断 owner 决定；64 个 policy 槽既未覆盖也未批准，等待 D-01；在飞未跟踪补充件中的 41/56 frame 与 14/56 datum 绑定在此不作为证据引用。
