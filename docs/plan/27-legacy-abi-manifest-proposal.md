# #27/#73 旧 ABI manifest 提案模板与门禁（离线）

2026-09-12。本切片把 #58 关闭时列出的"进入 ABI 实施票的五项前置"操作化为一个可机审的提案对象 + fail-closed 校验器。

> [!CAUTION]
> **本门禁不能批准任何 ABI**：
> 结构完整的提案也只能得到 `gate=proposal_structure_only`、`status=blocked_unapproved`、`acceptance=false`。
> **CLI exit 0 仅表示“结构完整、可供 Astra/用户审阅”，绝对不代表 ABI 通过，严禁在任何脚本、流程或文档中将 exit 0 解释为 ABI 验收或通过。**

## 文件

- `docs/plan/27-legacy-abi-manifest.schema.json` — manifest 结构合同（Draft 2020-12），包含完整六状态生命周期、`unresolved_conflicts`（`minItems: 2`, `uniqueItems: true`）、`error_codes`（`minItems: 1`）、数组指针强约束与规范相对路径正则。
- `tools/validate_legacy_abi_manifest.py` — 词法 + schema + 语义校验器；`validate(path) -> report`；CLI `python3 -B tools/validate_legacy_abi_manifest.py MANIFEST [--output REPORT]`，结构合法提案 exit 0，任何违反 exit 2。
- `validation/test_validate_legacy_abi_manifest.py` — 23 项正负纯测试，覆盖词法重复键/NaN、生命周期图、相对路径安全、Unicode 文本与规范化别名、冲突唯一性与 CLI 行为。

## 提案必填内容（对应 #58 五项前置）

| #58 前置 | manifest 位置 | 强制校验点 |
| --- | --- | --- |
| 1. 导出名/调用约定/参数指针/数组长度/类型/返回与错误码 | `exports[]` | 导出名与参数名唯一；`return.type`+非空 `error_codes`；参数顺序恰为 0..n-1；数组参数必须 `type='pointer'` 且绑定非 none `element_type` 与正 `length` |
| 2. 单位/坐标/时间/所有权/写入时机 | `exports[].units/ownership/sample_phase/step_semantics` | 四者全枚举强制，拒绝占位词；`exports` 整体必须诚实覆盖已知 `init/input/step/output/reset/terminate` 能力，证据不足则显式标明 unresolved，禁止虚构导出 |
| 3. 生命周期状态图 | `lifecycle` | `states` 必须恰含 `unloaded/loaded/initialized/stepping/resetting/terminated` 六状态；`transitions` 严格 `from->to` 语法且节点属于 `states`，从 `unloaded` BFS/DFS 可达全部六状态；`reset_restores_random_state` 枚举强制 |
| 4. 崩溃/错误隔离 | `isolation` | dll_crash/step_error/short_output/repeated_reset/thread_udp_residue 五项全填非空、非 `unknown`/`todo`/`n/a` 等占位说明 |
| 5. 样本 SHA/来源/许可/本机使用范围/可读头或包装源 | `sample` | 五键全非占位；`file_sha256` 64 位十六进制；`readable_header_or_wrapper` 必须为规范相对路径 |

每导出与冲突还须 `evidence{path, sha256, lines}`：
- `path` 必须为仓库内规范相对路径：禁止以 `/` 或盘符开头、禁止反斜杠 `\`、禁止目录遍历 `..` 或 `.`、禁止空段和空白、禁止 NUL 字节。
- `lines` 必须为从 1 开始、非颠倒且单调递增的行号区间（如 `1-10` 或 `1235-1239,1292-1296`）。

## 已知冲突的强制建模

两个 SDK 消费端硬冲突（证据 SHA `0a2a30e9…`）必须在 `unresolved_conflicts` 中声明，且 `id`、`description`、SDK consumer `evidence.path`、SHA 与行号均固定，`adjudication` 只能为 `unresolved`：

1. `dllinputcolls-width` — description 固定为 `DllInputColls declared double[20] then overwritten as float[20] in the SDK consumer`，SDK consumer path 固定为 `RflySimSDK/ctrl/DllSimCtrlAPI.py`，行号为 1235-1239、1292-1296；
2. `dllinitposang-name` — description 固定为 `consumer checks DllInitPosAngStat but accesses DllInitPosAngState`，SDK consumer path 固定为 `RflySimSDK/ctrl/DllSimCtrlAPI.py`，行号为 1248-1255。

冲突集合必须恰好覆盖这两项（禁止缺失、禁止额外未定义冲突、禁止重复 ID、禁止改标 resolved）。裁决属于用户/Astra 决策票，不属于本门禁。

## 词法与解析安全

- 校验器在读取 JSON 时通过词法钩子严格拒绝**重复 JSON 键**（避免 Key Shadowing 规避审查）。
- 词法拒绝 `NaN`、`Infinity`、`-Infinity` 常量。
- 所有字符串（包括嵌套对象中的必填字段与字符串数组项）必须在 `strip()` 后非空，并拒绝 Unicode `Cc/Cf/Cs/Co/Cn` 控制、格式、代理、私用和未分配字符；占位词比较统一使用 NFKC + `casefold()`，但不会改写 manifest。
- 路径本身及每个路径段都必须通过同一占位词检查；路径段必须已经是 NFKC 规范形式，除相对路径、分隔符和遍历规则外，不接受不可见字符或规范化别名。

## 填充指引

1. 复制本模板结构，逐导出填写；任何 "unknown/todo/n/a" 占位被样本链与导出检查拒绝。
2. 每个字段必须有可读头文件/包装源证据行；二进制字符串证据（`model-reference-provenance-supplement.md` 的 e1 导出名单）可作 `evidence.path` 的一部分，但若无法确定内部映射必须显式保留 unresolved 描述，绝不能自行虚构导出原型。
3. 校验器通过 ≠ 批准。批准后由 Astra 按 #73 票面实施 `Simulator/wksim_plugins/` 三件交付。

## Non-claims

- 不加载/执行/修改厂商 DLL 或安装；不推断许可；不分发厂商材料。
- 不声称旧或新 ABI 已批准；不解除 #73/#74/#27；不触碰 `wk_model_*` 自主核心边界。
- 校验器通过（CLI exit 0）不构成互操作证明、数值正确性、ABI 兼容证明或 #6/G6 预算满足。
