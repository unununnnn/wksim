# #26 原五项 AC 证据映射（当前源码）

2026-09-12；模块 DS-D；仓库 `unununnnn/wksim`。
本文件用**当前真实原件**把 #26 的**原五项验收标准**逐条映射到精确证据、给出判定与未覆盖项。
不修改任何历史 pin manifest，不把"文件存在"当作许可成功，不重跑 native/编译/模型加载。

证据根：
- `R = validation/codegen-e0-build-current-wrapper-01/`（当前 wrapper 冷构建，实测）
- `L = validation/codegen-e0-lifecycle-current-wrapper-01/`（当前 wrapper 独立 native 生命周期，实测）
- `G = validation/codegen-e0/short-cycle-codegen-01/`（既有生成/许可阶段证据，只读引用）
- `H = validation/codegen-e0-build-short-cycle-01/`、`validation/codegen-e0-lifecycle-01/`（历史证据，只读，**未改**）

---

## 1. 前置裁决：两条票依赖的实时状态

本次以 `gh issue view --repo unununnnn/wksim` 实时核验：

| 票 | 状态 | stateReason | closedAt | 对 #26 的意义 |
| --- | --- | --- | --- | --- |
| **#24** | **CLOSED** | COMPLETED | 2026-09-09 02:38:40 | #26 的 Blocked-by 之一，**已满足** |
| **#9** | **OPEN** | — | — | #26 的 Blocked-by 之一，**仍未满足** |
| #26 | OPEN | — | — | 本票仍开放 |
| #70 | CLOSED | COMPLETED | 2026-09-10 15:06:54 | 子票（来源/合同） |
| #71 | CLOSED | COMPLETED | 2026-09-10 15:06:59 | 子票（生成/构建） |
| #72 | CLOSED | COMPLETED | 2026-09-10 15:07:05 | 子票（无 MATLAB 导入/冷重建） |

**#24 的关闭依据**（引自其关闭评论，仅引用不重跑）：主代理已按原 AC1–AC5 复核，完成质量可编辑 Quad X 的保存/重载、导出/导入、独立构建及真实静态响应交付；1.515→1.818 kg、相同四通道 0.8、500×1 ms 后上升速度 5.175467→3.606483 m/s、高度 1.196241→0.822130 m；500 个电机转速样本完全一致，导入重建 500×120 输出完全一致；54 项源码/证据哈希复核、6 项单元与 10 项 native 静态/拒绝检查通过。

**#9 未满足**：其 label 为 `wayfinder:grilling`，属待人类裁决的接口决策，未产出可机器判定的结论。

> 结论：**父票关闭条件 = 原 AC 全部满足 + 原 Blocked-by 全部满足**。当前 AC 侧见第 3 节，依赖侧**至少 #9 未满足**，故 #26 **不可关闭**。

---

## 2. 原五项 AC（GitHub #26 正文逐字）

1. 完整记录可编辑材料、生成产物、编译工具、导入模型和运行证据的来源链。
2. 复用本机MATLAB/Simulink构建工具时实际检查可用性，不把文件存在当作许可检出成功。
3. 生成后关闭MATLAB，核心仍独立加载、运行、重置和终止该模型。
4. 厂商材料留在受控本地来源，不提交授权不明生成源码；不把旧ZIP直接编译称为已验证完整生成流程。
5. 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

---

## 3. 逐条映射

### AC1 · 来源链完整记录 —— 判定：**满足（本地范围）**

| 环节 | 精确证据 | 值 |
| --- | --- | --- |
| 可编辑材料 | 冻结记录 `validation/coordination/native-inputs-20260912/current-lifecycle-01.json`（`1e28021eaf0f573b3ad3db22d89c58bc89e31da8599b6bd194e49d3e54d80a55`） | 记录 43 项输入/历史哈希 |
| 生成产物 | 生成源六件（经 `/root` 原生复核） | `model.cpp` = `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290`（4070 B，**当前 wrapper**）；`Exp1_MinModelTemp.cpp` = `2c25b3fa…`；`Exp1_MinModelTemp.h` = `7601dbd7…`；`rtwtypes.h` = `1b08664b…` |
| 编译工具 | `R/build-manifest.json`（`434d1745924f9b0a4910a034e1b4847476e02ccde1c7b06f020087880c1f9226`）· `toolchain` | `g++ (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0`；`-std=c++17 -O2 -fno-fast-math -fPIC -shared -Wl,--no-undefined` |
| 导入模型 | `L/audit.json`（`0b5d96c97fcba5120213a2143ca641375878140435bc681b58ea3fcef8c5ff29`）· `source_sha256` + `library_sha256` | 六源哈希与库 `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328` 全部交叉绑定 |
| 运行证据 | `L/original/cycle-0..1.jsonl`、`L/cold/cycle-0..1.jsonl` | 4 份 raw 文件**实测哈希同为** `0979200da666f80d679203f07c47effd5d7385d3a0ddb1fe2b30e1bbc70b7553` |
| 冷重建绑定 | `L/audit.json` · `cold_library` = `/root/wksim-codegen-e0-cold-907225b3b06c/libwksim_e0.so` | 与 `library_sha256` 同值（见 AC3） |

**证据链闭合性**：每个环节都有具名路径 + SHA256，且 `L/audit.json` 内部把 `source_sha256` 与 `library_sha256` 交叉绑定到 `R/build-manifest.json` 的 staged 源。**无环节仅凭文件名或存在性支撑。**

**残留（如实列出）**：AC1 本身不要求审查导入器语义，但上游文档记录 `tools/quad_model_parameters.py build` 仍固定校验旧 ZIP 与五个旧成员 SHA，**不是**通用新生成源码导入器（见 `docs/plan/26-generation-contract.md` §3）。本次未复核该导入器，故不对其作任何断言。

### AC2 · 实际检查工具可用性，不把文件存在当许可检出 —— 判定：**满足（按记录，未重跑）**

| 项 | 精确证据 | 值 |
| --- | --- | --- |
| 许可 test/checkout | `G/codegen-report.json`（`e5f32bd2890137591b61eba72fe0b21893fef578fd0a57094baf8fe92398f822`）· `licenses` | 5 项产品 `SIMULINK` / `Real_Time_Workshop` / `RTW_Embedded_Coder` / `Aerospace_Blockset` / `Aerospace_Toolbox`：`test` 全为 `1`，`checkout` 全为 `1` |
| 阶段结果 | 同上 · `stages` | 9 阶段（`license_verification` … `close_model`）全为 `ok`；报告 `status` = `generated` |
| 汇总 | `G/summary.json`（`42bc11a2a55fc26542cb52d34fc22d7ae8b3c6fc66deec19708aa232eb910f7c`） | `matlab_return_code=0`、`stages_ok=true`、`licenses_ok=true`、`timed_out=false`、`cleanup_unverified=false` |
| MATLAB 控制台 | `G/matlab-console.log`（存在，未作为许可证据使用） | 仅作旁证 |

**为什么这不是"文件存在"**：判据是 `licenses.test` 与 `licenses.checkout` 的实测返回 `1`，以及 `license_verification` 阶段 `status='ok'`——即真实 test 与真实 checkout 的结果，而不是"装了什么文件"。**原文明令**"不把文件存在当作许可检出成功"，本映射据实测返回值判定。

**边界（必须与判定并列）**：本次**未重跑** MATLAB。AC2 的证据来自既有 `G` 快照；**首次** wrapper 构建（`R`）与生命周期（`L`）阶段不涉及 MATLAB 调用。

### AC3 · 无 MATLAB 独立加载、运行、重置、终止 —— 判定：**满足（本次实测新增，覆盖当前 wrapper）**

| 判据 | 精确证据 | 值 |
| --- | --- | --- |
| 冷重建后加载运行 | `L/audit.json` · `status` / `schema` | `pass` / `wksim.generated-e0-lifecycle.v1` |
| reset 覆盖 | `L/audit.json` · `ticks_per_cycle` / `cycles` / `compared_values` | `1000` / `4` / `480000`（= 4×1000×120） |
| 四份 raw | `L/audit.json` · `raw_sha256` + 实测重算 | 四份**同为** `0979200d…` |
| 两次独立进程 | `L/audit.json` · `runs[*].identity` | original `pid=705, pgid=705, start_ticks=196595`；cold `pid=706, pgid=706, start_ticks=196622` |
| 退出码 | `L/audit.json` · `runs[*].returncode` | 均为 `0` |
| 构建产物同一性 | `L/audit.json` · `library_sha256` | `528db324…`，与 `R/summary.json` 记录同值 |
| 终止/资源收尾 | `L/original/process.json`（`cccd828a3e6444981f44cc6388e4c215f0339ca530f66c8fcf07071d5c4097b7`）、`L/cold/process.json`（`39f809482e06b590fa6fcd090accaeb9311decb34dfead22d575c1513fcc44e6`） | 记录进程身份与加载映射 |
| 无 MATLAB 动态依赖 | `R/ldd.txt` | `clean=true`、`violations=[]`；依赖仅 `linux-vdso.so.1`、`libstdc++.so.6`、`libm.so.6`、`libc.so.6`、`ld-linux-x86-64.so.2`、`libgcc_s.so.1` |

**这是本次唯一"新覆盖"的 AC**：先前的生命周期证据（`H`）绑定的是**旧 wrapper**（`3f325678…` / 1864 B）。本次 `L` 绑定**当前 wrapper**（`150ddf3b…` / 4070 B），因此 AC3 在"当前源码"意义上是新覆盖的。

**上界（证据自身声明）**：`L/audit.json` · `limitation` = "Independent Linux reconstruction and reset only; no flight or MATLAB numeric oracle"。即：**不**证明物理正确性，**不**证明飞行。

### AC4 · 厂商材料受控，不提交授权不明源码，不把旧 ZIP 编译当生成 —— 判定：**满足**

| 判据 | 精确证据 | 值 |
| --- | --- | --- |
| 生成源码未入库 | `git ls-files` 对生成源码路径无匹配（本次实测） | `Exp1_MinModelTemp*` / `ert_rtw` 均不被跟踪 |
| 厂商输入未改动 | `G/post-source-verification.json` | `MulticopterModel.zip` `d528b5d2…`、`Exp1_MinModelTemp.slx` `c232e2e9…`、`Exp1_MinModelTemp_init.m` `9ca09a95…`，三项 `unchanged=true` |
| 暂存未改动 | `G/post-staged-verification.json` | 同类 `unchanged=true` |
| 本次未复制厂商字节 | `R` 与 `L` 目录清单 | 仅含项目文档/哈希/日志/raw jsonl 与项目自有 `.so`；无厂商 SLX/ZIP/DLL |
| 旧 ZIP 未被称作生成 | `R/build-manifest.json` · `generation_run_id` | = `short-cycle-codegen-01`（**新生成**运行），而非旧 ZIP 成员 |

**未做的事（不构成不满足）**：本次未评估厂商材料的**再分发**许可。AC4 只要求"留在受控本地来源、不提交、不把旧 ZIP 编译当生成"，三条均满足；再分发是独立问题，见第 5 节。

### AC5 · 交付命令/身份/结果/失败边界；主代理复核后才能关闭 —— 判定：**部分满足（复核记录缺失）**

| 要求 | 证据 | 状态 |
| --- | --- | --- |
| 实际命令 | `R/command.json`、`L/build.json`（`238f64d9a512a353854281c489d39f5ea3db9a9dfb3139f7264981e77cdce648`）、`G/command.json` | 满足 |
| 版本/身份 | `R/build-manifest.json` toolchain；`L/audit.json` runs[*].identity | 满足 |
| 预期与结果 | `L/audit.json` status/schema/cycles/compared_values；`R/summary.json` 探针字段 | 满足 |
| 失败边界 | `L/audit.json` limitation；`L/*.log`（空）；`R/build.std{out,err}.log`（空） | 满足 |
| **主代理复核记录** | **不存在**（本次未发现任何具名复核/批准工件） | **缺证** |

**因此 AC5 未闭合**，且它同时是"父票关闭"的必要条件之一。

---

## 4. 来源证据链：原 #70/#71/#72（按原件引用，不重跑）

### 4.1 子票状态与写入范围（原件引用）

| 票 | 标题 | 写入范围（正文原文） | 状态 |
| --- | --- | --- | --- |
| #70 | 确定一个实际可用的模型生成来源及合同 | `docs/plan/26-generation-contract.md (new)` | CLOSED |
| #71 | 生成并构建一个已批准模型 | `validation/lunar-26-generate-build/ (new evidence)` | CLOSED |
| #72 | 验证无MATLAB依赖导入与一次冷重建 | `validation/lunar-26-import-reset-run/ (new evidence)` | CLOSED |

### 4.2 合同原件要点

`docs/plan/26-generation-contract.md`（`6a8e7eace06581bcd74d7e68a017bcffcc60c74c862172c058f6e149e2855d20`）明确：

- **来源选择**：固定 e0 SLX 11.8 + 原 init 作 normal 参考；由同一冻结副本新生成并独立编译的 native 作候选；`Exp1_MinModelTemp.slx` = `c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392`、init = `9ca09a95bda57eee54eb6ba99982d091006ade28b6df1ef7446eb17b73de9991`、旧 ZIP 11.0 = `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`。
- **11.8 ≠ 11.0**："11.8 与 11.0 不构成同版本配对，不复用 11.0 输出当作 11.8 的预期数值。"
- **导入与生命周期合同**：C 入口 `create` 初始化并清输入、`step` 每次 1 ms、`destroy` 执行 terminate；输出 120 double 按 `Vehicle60 / Sensor30 / GPS30`；返回 `0` 成功 / `1` 非法参数 / `2` 模型错误 / `3` 非有限状态；reset 采用终止旧进程后冷重建，新 `run_id`/PID 且不宣称进程内热 reset。
- **历史阻塞结论**：`blocked_source_authorization_and_generation_entry`（文首 §1 称其为历史检查点；本文只引用，不据其下结论）。
- **许可边界**：§1 明示"没有…允许本项目生成/修改/独立运行产物的条款或权利人确认"，属**有界搜索结果**；§2 要求"允许本机使用与允许再分发分开记录"；§3 要求解除来源阻塞需明确 `local_generate/local_modify/local_compile/local_run` 与 `redistribute_source/redistribute_binary` 六项。

### 4.3 依赖方在 #24 上的复用声明

合同 §23 段（引用 #24 主复核）表明 #70 复用了 #24 的身份检查与静态响应证据，并声明"此次未重跑，不能将历史统计计为本轮测试"。本映射沿用同一纪律：**只引用，不重跑，不把历史统计计为本轮**。

---

## 5. 许可证与授权：明确未证部分

| 问题 | 现状 | 依据 |
| --- | --- | --- |
| 工具许可 test/checkout | **已证**（5 项 test=1、checkout=1，9 阶段 ok） | `G/codegen-report.json` |
| 绑定 SLX/init 哈希的**权利人/条款** | **未证**：搜索无匹配，属有界搜索结果 | `26-generation-contract.md` §1 |
| 六项权限（local_generate/modify/compile/run、redistribute_source/binary） | **未逐项记录** | 同上 §3 |
| 再分发权（厂商 SLX/init/生成 C++/MathWorks 头/DLL） | **未证，且不得由本地可用性推定** | 同上 §2 |
| 厂商字节是否泄漏进仓库 | **未泄漏**（生成源码未跟踪；本次证据目录只含项目文档/哈希/日志） | 第 3 节 AC4 |

**红线**：本地 `test=1`/`checkout=1` 与"一次本地构建成功"**都不得**被表述为再分发许可。本文件不复制任何厂商源码或二进制。

---

## 6. 新覆盖 vs 未覆盖

### 6.1 本次**新覆盖**

| 项 | 覆盖内容 | 证据 |
| --- | --- | --- |
| **当前 wrapper 的 cold/reset 生命周期** | 当前 wrapper（`150ddf3b…`/4070）冷重建后独立加载、运行 4×1000、reset、终止；四份 raw 同哈希 | `L/audit.json`、`L/*/cycle-*.jsonl` |
| **当前 wrapper 的构建身份绑定** | 新 build manifest 记录当前 wrapper 哈希与大小 | `R/build-manifest.json` |
| **无 MATLAB 运行依赖** | `ldd` 干净、无 matlab/simulink/libmw/mcr/rflysim | `R/ldd.txt` |
| **构建与生命周期期间的输入/历史不变** | 43 项前后哈希一致 | 冻结记录 `1e28021e…` |

### 6.2 本次**未覆盖**（明确声明）

| 未覆盖项 | 为什么未覆盖 | 归属 |
| --- | --- | --- |
| **新增 terrain 接口** | wrapper 的 `Expose same-source terrain input`（`f9a34f8`）**未被本次探针驱动**：探针为常量输入、证据文件中无 `terrain` 相关量 | 需单独验收 |
| **新增"已初始化态"语义** | `Expose initialized model state`（`9bb11ce`）无对应断言 | 需单独验收 |
| **G6 / 物理精度 / R1** | `L/audit.json` limitation 自述无 MATLAB 数值 oracle；本链只做构建与生命周期，**不做任何数值比较** | #59 / G6 路线；R1 `numerical_failed` 与 5684 失败值**原状** |
| **可选旧/新 ABI DLL** | 使用项目自有 C 入口语义（`wk_model_create/step/destroy`），**不涉及**厂商 DLL ABI | #27 / #28；受 #9 阻塞 |
| **导出/字段布局全量审查** | 探针只验证 120 维、有限性、时钟 ±1e-8 | 合同要求独立审查 |
| **飞行 / 真实 SITL / UE 显示** | 本链无飞控、无 UE、无 ROS | 其他票 |
| **其余构型与机型** | 仅 e0 四旋翼样本 | Full 台账 MODEL-* |
| **导入器语义复核** | 未运行 `tools/quad_model_parameters.py`，不对其作断言 | 上游缺口 |

---

## 7. 判定汇总

| AC | 判定 | 关键依据 | 未闭合点 |
| --- | --- | --- | --- |
| AC1 来源链 | **满足（本地）** | 六源+库+四 raw 均有 SHA256 且交叉绑定 | 导入器语义未复核（AC 不要求） |
| AC2 许可实测 | **满足（按记录）** | 5 项 test=1/checkout=1；9 阶段 ok | 本次未重跑 MATLAB |
| AC3 无 MATLAB 生命周期 | **满足（本次新覆盖当前 wrapper）** | `L/audit.json` pass；4×1000；480000 值；四 raw 同 `0979200d…`；两进程 705/706 独立、return 0 | 无飞行、无数值 oracle |
| AC4 厂商材料受控 | **满足** | 生成源码未跟踪；厂商输入 `unchanged`；新生成非旧 ZIP | 再分发权未评估（AC 不要求） |
| AC5 交付与复核 | **部分满足** | 命令/身份/结果/边界齐备 | **主代理复核记录缺失** |

### 仍不可宣称（第 7 节推导）

- **#26 不可关闭**：AC5 缺复核记录，且 **#9 仍 OPEN**（实时核验）。
- 不可由 AC3 的通过推断物理正确、G6 通过、terrain 已验收、或 AC1–AC4 全由本次执行覆盖（AC1/AC2/AC4 部分依赖既有快照）。
- 不可把本次新哈希"更新"进旧 manifest 使历史看似执行了当前源码：旧证据（`H`）与旧 `docs/plan/26-closure-readiness-manifest.json` **保持原值**，本次全部新证据另立目录。
- 不可用本文件替代 #60 的 `docs/plan/full-acceptance-report.md`。

---

## 8. 冻结与不变量（本轮）

| 项 | 值 |
| --- | --- |
| 本轮冻结的 validator | `tools/validate_generated_e0_lifecycle.py` = `ec883644acce248921c9775451699ce2c149311d438b720e3e21c361571a2098`（已主审 + codebuddy 审，**不再改**） |
| 当前 wrapper | `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290` / 4070 B |
| 当前库 | `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328` / 87584 B |
| 四份 raw | 同为 `0979200da666f80d679203f07c47effd5d7385d3a0ddb1fe2b30e1bbc70b7553` |
| 生命周期收据 | `validation/coordination/native-inputs-20260912/current-lifecycle-01.json` = `1e28021eaf0f573b3ad3db22d89c58bc89e31da8599b6bd194e49d3e54d80a55` |
| 旧证据（`H`、旧 manifest、生成合同） | **未改**，逐字节保持 |

**外层 shell 收尾说明**：本次执行的外层 shell 在**全部验证与哈希检查完成之后**出现一条多余的 CR 命令并返回 `exit 1`（`bash: line 41: carriage-return command not found`）。该失败发生在 native validator 完成与 post-validation 哈希检查完成**之后**，属外壳收尾噪声；`native_rerun_required = false`，native **无需重跑**。
