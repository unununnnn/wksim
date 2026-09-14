# DS-D / D2 · #26 模型收口只读交叉核验

2026-09-12；工作区 `C:/Users/PC/Documents/odid编译/wksim`；HEAD `7126d4d774a33c7d4b2504b9931a93ac27d7fa51`（2026-09-12 20:01:49 +0900）。

本文件是对 `docs/plan/26-closure-readiness-manifest.json`、`docs/plan/26-generation-contract.md` 与现有源码/记录的**只读交叉核验**，面向主会话给出可执行的收口/补证条件。它不重新生成、不编译、不运行 MATLAB，不复制或披露厂商源码或二进制，不关闭任何 Issue 或 Goal，也不修改上述两个既有文件。

配套产物：`docs/coordination/ds-full-frontier-20260912.json`（D1，Full 剩余依赖与模型分支前沿）。本文件不替代 #60 声明的交付文件 `docs/plan/full-acceptance-report.md`（该文件当前不存在）。

---

## 1. 核验方法与边界

| 项 | 内容 |
| --- | --- |
| 读取方式 | 按已知路径直接读取；未扫描整个 workspace |
| 重算方式 | `Get-FileHash -Algorithm SHA256` 对清单 pin 逐项对当前 checkout 重算 |
| 未执行 | MATLAB、Embedded Coder、g++、Python 验证器、飞控/SITL、ROS1/ROS2、UE、任何模型 step |
| 厂商字节 | 未读取、未复制、未披露任何厂商源码/二进制；文中只引用仓库内已有的 SHA256 与路径字符串 |
| 状态来源 | Issue 状态来自本次真实 `gh issue view --repo unununnnn/wksim`；不是对 `ready-for-agent` 标签的复述 |

## 2. 清单 pin 逐项重算（6/6 命中）

`docs/plan/26-closure-readiness-manifest.json` 的 5 组 `acceptance_evidence` 共 pin 了 6 个文件。全部存在，且 SHA256 与清单逐字节一致：

| 清单验收项 | 路径 | 期望 SHA256 | 本次重算 | 结果 |
| --- | --- | --- | --- | --- |
| source_chain | `docs/2026-09-10-generated-e0-lifecycle.md` | `60a223620e7f…43d7a` | 同 | 命中 |
| source_chain | `validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json` | `85c40213cec0…acc67` | 同 | 命中 |
| matlab_license_actual_checkout | `validation/codegen-e0/short-cycle-codegen-01/codegen-report.json` | `e5f32bd28901…98f822` | 同 | 命中 |
| matlab_free_lifecycle | `validation/codegen-e0-lifecycle-01/audit.json` | `3d5c7896de10…1aed346d` | 同 | 命中 |
| vendor_materials_controlled | `validation/codegen-e0/short-cycle-codegen-01/summary.json` | `42bc11a2a55f…10f7c` | 同 | 命中 |
| delivery_identity | `validation/codegen-e0-build-short-cycle-01/build-manifest.json` | `0669730aeff5…7aa1c` | 同 | 命中 |

**结论**：清单 pin 本身没有漂移，也没有被事后改写。这批证据是真实存续的。

### 2.1 pin 内容对清单断言的支撑（已读原文复核）

| 清单断言 | 证据原文 | 判定 |
| --- | --- | --- |
| `matlab_license_actual_checkout` 要求 `stages[license_verification].status == 'ok'` | `codegen-report.json` 9 个阶段全部 `ok`（license_verification, fileGenControl, load_system, verify_solver, configure_target, initialization, slbuild, artifact_verification, close_model）；`report.status = generated` | 满足 |
| `matlab_free_lifecycle` 要求 `status == 'pass'` 且两次独立进程身份 | `audit.json`：`status=pass`、`schema=wksim.generated-e0-lifecycle.v1`、`cycles=4`、`compared_values=480000`；`original` pid 693 与 `cold` pid 694，`returncode` 均 0 | 满足 |
| 同一 .so 字节 | 两次运行 `library_sha256` 均为 `7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e`；`build-manifest.json:output_library` 同值，`size_bytes=87312` | 满足 |
| `vendor_materials_controlled`：受控本地来源、无授权不明生成源码入库 | `git ls-files` 中不存在任何 `Exp1_MinModelTemp*` / `ert_rtw` 生成源码；`post-source-verification.json` 三个厂商输入 `unchanged=true`（SLX `c232e2e9…`、init `9ca09a95…`、ZIP `d528b5d2…`） | 满足 |

### 2.2 生成源码链的本地可追性（补充命中）

清单只 pin 了 manifest 文件，未 pin 生成产物本身。本槽额外核验了 `work/` 下的暂存产物：

| 生成文件 | pin 值 | 当前 `work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw/` 重算 | 结果 |
| --- | --- | --- | --- |
| `Exp1_MinModelTemp.cpp` | `2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274` | 同 | 命中 |
| `Exp1_MinModelTemp.h` | `7601dbd721f0502e4bd67758d86cc21abf8e5c9568a31fb3160283df1df8c4bc` | 同 | 命中 |
| `rtwtypes.h` | `1b08664b70d40d08ee2952ca47254bd16a9e045be8b5edc9781fe620fb7c199f` | 同 | 命中 |

即：**生成侧**（SLX 11.8 → 新 C++）在本 checkout 内可自查；`audit.json` 中 `Exp1_MinModelTemp.cpp` 的 pin 与此完全一致。

同时确认两个非 pin 的同名文件属于不同链路，不构成 pin 漂移：

- `validation/quad-parameters-native-20260909-b/tampered-build/Exp1_MinModelTemp.cpp` = `a35d7c8f…` —— 名称即 `tampered-build`，是负例构造物；
- `work/e0-major-staging-parent-final-01/Exp1_MinModelTemp.cpp` = `993f33ea…` —— major 采集暂存链，不是 codegen-01 产物。

## 3. 发现的实质漂移：wrapper `model.cpp` 与 pin 不一致

这是本次核验最重要的新发现，直接命中清单自述的 `Current-checkout provenance, wrapper, and lifecycle revalidation` 缺口。

### 3.1 pin 的 wrapper 是旧版

`build-manifest.json:staged_sources["model.cpp"]` 记录：

```
source_path     C:\Users\PC\Documents\odid编译\wksim\Simulator\wksim_core\model.cpp
sha256          3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c
size_bytes      1864
```

该 pin 与 `audit.json:source_sha256["model.cpp"]` 完全一致，说明 2026-09-10 的 `libwksim_e0.so` 是**与 1864 字节的 wrapper 一起**编译的。

### 3.2 当前 checkout 的 wrapper 已不同

| 项 | 值 |
| --- | --- |
| 当前 `Simulator/wksim_core/model.cpp` SHA256 | `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290` |
| 当前文件大小 | `4070` bytes（对比 pin 的 1864 bytes） |
| 工作树 vs HEAD | `git diff --stat -- Simulator/wksim_core/model.cpp` 为空 → 工作树内容等于 HEAD `7126d4d` 提交内容 |
| HEAD 内容 SHA256（经 `git show HEAD:…` 导出后重算） | `68c6965bb52c37afb68c6881ba948787b701698a9f3ae85f509c6694a29ff2d5` |

### 3.3 漂移原因（非偶然）

`git log -- Simulator/wksim_core/model.cpp` 显示 pin 之后有两个**功能性**提交改动了该文件：

| commit | 说明 |
| --- | --- |
| `9bb11ce` | `Expose initialized model state` |
| `f9a34f8` | `Expose same-source terrain input` |

因此当前 wrapper 比 pin 版本多出约 2.2 KB 的功能改动，且至少引入“暴露模型初始化态”与“同源地形输入”两条新语义。

### 3.4 这条漂移的精确含义

必须把两件事分开，否则会得出错误结论：

- **不成立的推论**：不能说“`libwksim_e0.so` 的生命周期证据失效了”。该 .so 的字节、其编译命令、其输入 pin 都自洽（见 §2.1、§2.2），历史证据对它自身仍然有效。
- **成立的事实**：pin 住的 wrapper 与当前 checkout 的 wrapper **不是同一个源**。所以“当前 checkout 能否复现/加载该模型”这个问题，不可能仅凭既有证据回答——因为既有证据证明的是**旧 wrapper** 的行为。

这正是清单 `claim` 字段所要求的 `current-checkout provenance, wrapper and lifecycle artifacts must be revalidated`。本槽的贡献是把它从一句自述，变成了可执行、可判定的具体条件（见 §5 条件 B）。

## 4. 五条父 AC 的逐项判定

| AC | 原文摘要 | 判定 | 依据 | 残留缺口 |
| --- | --- | --- | --- | --- |
| AC1 | 完整记录可编辑材料、生成产物、编译工具、导入模型和运行证据的来源链 | 已证（本地） | §2 全部命中；`source-manifest.json`、`generated-sources-manifest.json`、`build-manifest.json`、`codegen-report.json` | “导入模型”一环的**当前**导入器身份未复核：`26-generation-contract.md:29` 指出 `tools/quad_model_parameters.py build` 仍固定校验旧 ZIP 与五个旧成员 SHA，不是通用新生成源码导入器 |
| AC2 | 实际检查 MATLAB/Simulink 可用性，不把文件存在当许可检出成功 | 已证 | `codegen-report.json` license_verification=ok；`summary.json licenses_ok=true, matlab_return_code=0, timed_out=false` | 本项只覆盖 test/checkout；不覆盖再分发权（不属本 AC） |
| AC3 | 生成后关闭 MATLAB，核心仍独立加载、运行、重置和终止 | 已证（外部构件） | `audit.json` pass、4 cycles、480000 值比较、两进程身份 | 构件在仓库外（`/root/wksim-codegen-e0-build-short-cycle-01`、`/root/wksim-codegen-e0-cold-c96e30e01ec6`）；本 checkout 内不存在该 `.so`，无法就地复核字节。`audit.json:limitation` 自述仅 Linux 重建与重置，无飞行、无 MATLAB 数值 oracle |
| AC4 | 厂商材料留在受控本地来源，不提交授权不明生成源码 | 已证 | `git ls-files` 无生成源码；`post-source-verification.json` 三输入 unchanged | 只证明“未提交”，不证明“可分发”；再分发条款仍未评估 |
| AC5 | 交付实际命令、版本/身份、预期与结果、失败/未验证边界；**主代理复核后才能关闭** | **缺证（未闭合）** | 命令/身份：`command.json`、`driver-identities.json`；边界：`build.stderr/stdout.log`、`ldd_audit.clean=true` | 两点：(a) `26-generation-contract.md` 的结论 `blocked_source_authorization_and_generation_entry` 从未被任何后续文档显式撤回，只有文首 §1 称其为“历史检查点”；(b) **主代理复核/批准记录不存在**——本票 AC5 明确要求它 |

## 5. 收口条件（主会话可直接执行）

以下条件是**充分且可判定**的。全部满足后 #26 的 AC 侧即为闭合；依赖侧另见条件 D。

### 条件 A · 显式处置合同自身的阻塞结论

- 动作：在 #26 内（或一张新证据文件）显式写清 `blocked_source_authorization_and_generation_entry`（`26-generation-contract.md:7`）是**已解除**还是**仍有效**。
- 若判已解除：必须给出解除依据（哪份文档/哪次运行的哪一项，推翻了该结论的哪个具体理由：许可条款、生成入口、准入器三者之一）。
- 若判仍有效：不得据 #70/#71/#72 的 CLOSED 推断 AC5 满足。
- 判定方式：字符串 `blocked_source_authorization_and_generation_entry` 在 #26 的收口记录中带有明确的 superseded / retained 标记，而不是靠文首一句“历史检查点”代替。

### 条件 B · 当前 checkout 的 wrapper 与生命周期重核（替代路径二选一）

针对 §3 的 `model.cpp` 漂移，主会话必须**明确选择**一条，并记录理由：

- **路径 B1（保留历史证据 + 记录偏差）**：明确声明 `libwksim_e0.so`（`7da68532…`）与 `3f325678…` 版 wrapper 绑定，且该绑定**早于** `f9a34f8`/`9bb11ce` 两次 wrapper 变更；因此当前 checkout 的 wrapper（`150ddf3b…`/`68c6965b…`，4070 bytes）**未**被既有生命周期证据覆盖。随后把“当前 wrapper 的加载/运行/重置/终止”列为**新证据需求**，而不是把它算作已完成。
- **路径 B2（补做一次最小重核）**：在受控环境下用当前 wrapper 重新构建并重跑生命周期。这会**产生新证据目录**（不得覆盖 `validation/codegen-e0-lifecycle-01/`），且需要新的编译与运行——属于主会话的授权范围，不在本槽内执行。

- 无论选哪条，都必须写清：旧 `.so` 的 87312 字节与 `7da68532…` 不被新结果追溯改写；新结果另立身份。

### 条件 C · 补 AC5 要求的主代理复核记录

- 动作：产生一份具名的复核记录，包含被复核的 pin 清单（§2 六项 + §2.2 三项生成源）、复核结论、复核者身份、时间。
- 判定方式：AC5 的“主代理复核后才能关闭”有对应工件，而不是依赖本文件（本文件是 DS-D 独立核验，不是主代理复核）。
- 注意：本槽**只读**核验 pin，未评估导入器语义、未运行验证器；因此本文件不能充当 AC5 的复核记录。

### 条件 D · 原 Blocked-by 关闭

- `#9` 当前 **OPEN**（本次 `gh` 实时确认，2026-09-12），labels `[wayfinder:grilling]`。
- `#24` 已 CLOSED，依赖侧只剩 `#9`。
- 清单自身把这一点写成 `machine_decidable: true`，并且其 `state_source=pinned_github_issue_snapshot` / `realtime_check=not_performed_by_local_audit` —— 本槽已补上这次实时核对，**结论是阻塞仍然成立，不是过期快照**。
- 判定方式：`gh issue view 9 --repo unununnnn/wksim` 为 CLOSED，或主会话显式记录“以原生 `wk_model_*` C ABI 路线替代厂商 DLL ABI 决策”从而解除该形式依赖。

### 条件 E · 子票状态与父票状态的显式对齐

- 事实：#70、#71、#72 全部 CLOSED（2026-09-10），而 #26 正文仍写“阻塞未清除前不进入执行前沿”。
- 动作：在 #26 内说明三个子票各自覆盖了哪几条父 AC 的哪一部分，并明确指出**子票关闭不等于父票 AC 全满足**。
- 判定方式：存在一张子票→AC 映射表；禁止出现“子票全关闭 ⇒ 父票可关”的推断。

## 6. 收口条件矩阵

| 条件 | 阻塞对象 | 需要谁 | 本槽可否代做 | 判定方式 |
| --- | --- | --- | --- | --- |
| A 处置合同阻塞结论 | AC5 | 主会话 | 否（本槽只读） | 明确 superseded/retained 标记 |
| B wrapper 漂移处置（B1 或 B2） | 当前 checkout 可复现性 | 主会话（B2 需授权执行） | 否 | 记录所选路径 + 新/旧身份分离 |
| C 主代理复核记录 | AC5 | 主代理 | 否（本槽非主代理复核） | 具名复核工件 |
| D 关闭 #9 或替代 ABI 决策 | 父票形式依赖 | 人类裁决 | 否 | `gh` 状态或书面替代决策 |
| E 子票→AC 对齐表 | 父票收口一致性 | 主会话 | 否 | 映射表存在 |

## 7. 明确不得据此声称的结论

- 不得据 #70/#71/#72 CLOSED 声称 #26 原 AC 已全部满足。
- 不得把 `audit.json` 的 480000 值字节一致当作物理精度、G6 或数值等价通过（`audit.json:limitation` 已自述无 MATLAB 数值 oracle）。
- 不得把 `.so` 的 87312 字节可复现当作当前 checkout wrapper 可复现（§3）。
- 不得把本机可编译厂商 ZIP 表述为可公开分发。
- 不得把 SLX 11.8 与旧 ZIP 11.0 当作同版本配对复用期望值（`26-generation-contract.md:21`）。
- 不得用本文件替代 #60 的 `docs/plan/full-acceptance-report.md`。

## 8. 本槽未做的事（边界声明）

- 未运行 `tools/validate_generated_e0_lifecycle.py`、`tools/quad_model_parameters.py`、`validation/test_g6_budget_manifest.py` 或任何验证器。
- 未从 `validation/codegen-e0/short-cycle-codegen-01/` 反查生成时暂存目录（该目录现已只剩报告类文件，生成源码不在其中）——这是刻意的：既有 pin 完整即已足够判定漂移，进一步推断会越过只读核验的边界。
- 未核验 `docs/plan/tickets/16-generated-model-import.md`（本次直接使用 GitHub #26 正文作为 AC 来源）。
- 未修改 `26-closure-readiness-manifest.json`、`26-generation-contract.md` 或任何其他既有共享文档。
