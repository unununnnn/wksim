# #26 当前 wrapper 冷重核 — 计划与实测增量

2026-09-12；模块负责人 DS-D；仓库 `unununnnn/wksim`。

> ## ⚠️ 本文件曾被误截断，此处为诚实的重建
>
> **发生了什么**：本模块在一次脚本化编辑中把 `docs/plan/26-current-wrapper-recheck-plan.md` 从约 490 行截断为 84 行，丢失了原第 1–12 节正文，仅存第 13 节与一行运行说明。该文件从未被 git 跟踪，因此**没有**恢复源。
>
> **已核验的恢复尝试**（均失败，故不做重建全文的谎称）：
> - `git log --all -- <path>`：无任何历史记录；`git ls-files` 报 `did not match any file(s) known to git`。
> - `git stash list`：空。
> - `git fsck --lost-found`：只报出与本文件无关的既有 broken link。
> - 磁盘/临时目录中不存在任何副本或备份。
>
> **因此本文件不再声称是原计划的完整复制。** 下面只保留两类内容：(1) 仍然存在且可核验的原文段落（第 13 节与运行说明），(2) 从本模块自己的 `docs/coordination/ds-26-host-recheck-20260912.json` 与工作区实测中可直接核实的**事实增量**。原第 1–12 节的完整叙述**已丢失且不予伪造**。
>
> 丢失内容的要点以事实增量形式在下面第 B 节列出；若需要原计划的完整文字，只能由主会话决定是否重新撰写。
>
> 本文件及其相关核验**不重新生成、不编译、不运行 MATLAB**，不加载任何 `.so`/DLL，不修改共享 checker、模型源、旧 manifest 或 Issue。

---

## A. 准确入口（唯一需要的可执行信息）

### A.1 当前 wrapper 冷重核（已完成，保留形状）

```powershell
# 注意：外层 wsl 是 Windows 侧启动器；真正的命令在 bash -lc 之内。
# 该驱动与验证器都要求 Linux 宿主，不要在 Windows 上直接运行。
wsl -d Ubuntu-22.04 -u root -- bash -lc "cd /mnt/c/Users/PC/Documents/odid编译/wksim && /usr/bin/python3 -B tools/build_generated_e0.py --wrapper-source 'Simulator/wksim_core/model.cpp' --generation-dir 'validation/codegen-e0/short-cycle-codegen-01' --matlab-include-dir '/mnt/d/matlab/install date/simulink/include' --build-id 'current-wrapper-01' --evidence-root 'validation' --wsl-distro 'Ubuntu-22.04' --wsl-user root --wsl-build-dir '/root/wksim-codegen-e0-build-current-wrapper-01' --run-test --test-steps 100 --timeout 120"
```

### A.2 独立生命周期验证器的下一入口（**尚未执行**）

```bash
# 必须在 Ubuntu-22.04 内运行：run() 首行要求 sys.platform=='linux'，
# 且 /root 必须是真实绝对路径（Windows 上 Path('/root/...') 不是绝对路径）。
cd /mnt/c/Users/PC/Documents/odid编译/wksim
/usr/bin/python3 -B tools/validate_generated_e0_lifecycle.py \
  --manifest validation/codegen-e0-build-current-wrapper-01/build-manifest.json \
  --output validation/codegen-e0-lifecycle-current-wrapper-01
```

该验证器**不接受显式 library 参数**（没有 `--library`）：CLI 只有 `--manifest` / `--probe` / `--output`（`--probe` 是内部子进程模式）。"指定新库"只能通过指向新 build manifest 表达。`--output` 必须不存在。执行会产生真实 `g++` 编译、`ldd` 与 4×1000 步 native 运行，并新建 `/root/wksim-codegen-e0-cold-<uuid>`，属主会话授权范围。

### A.3 纯行为测试入口

```bash
# 同样只在 Linux 上有效
/usr/bin/python3 -B -m pytest validation/test_generated_e0_lifecycle_admission.py -q
```

---

## B. 事实增量（可核验，替代已丢失的原叙述）

### B.1 漂移事实

| 项 | 值 |
| --- | --- |
| 被历史证据 pin 的 wrapper | `Simulator/wksim_core/model.cpp` = `3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c`，1864 bytes |
| 当前 checkout wrapper | `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290`，4070 bytes |
| 工作树 vs HEAD | `git diff -- Simulator/wksim_core/model.cpp` 为 0 行 |
| 漂移来源 | pin 之后两次功能性提交：`f9a34f8 Expose same-source terrain input`、`9bb11ce Expose initialized model state` |

必须分开陈述：既有 `.so` 证据对它自身仍然有效；成立的是"pin 住的 wrapper 与当前 checkout 的 wrapper 不是同一个源"。

**被取代的旧状态**：此前"主会话未冻结入口 / #71 所需完整生成命令缺失"的结论**已被取代**。冻结记录原文为 "Main agent freezes existing build_generated_e0.py for this authorized current-wrapper cold build and 100-step lifecycle check only"；对应的命令即 `tools/build_generated_e0.py`。缺口 A 已解除，范围仅限本次 cold build + 100 步检查。

### B.2 本次实测结果（主会话执行，2026-09-12）

| 项 | 实测值 |
| --- | --- |
| 证据目录 | `validation/codegen-e0-build-current-wrapper-01/` |
| 新 `library_sha256` | `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328` |
| 新 `library_size_bytes` | `87584`（历史 `7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e` 为 87312） |
| 核心断言 | 新 `build-manifest.json` 的 `staged_sources.model.cpp.sha256` = `150ddf3b…`、`size_bytes` = `4070` —— **绑定的是当前 wrapper** |
| `status` | `tested`；`command.return_code` = `0` |
| 探针 | `success=true`、`steps_evaluated=100`、`step_size_seconds=0.001`、`sim_time_seconds=0.1`、`all_outputs_finite=true`、`non_finite_step=null`、`output_dimension=120` |
| `ldd_audit` | `clean=true`、`violations=[]`（无 matlab/simulink/libmw/mcr/rflysim） |
| 审计上界 | `full_or_g6_acceptance: false`；`summary.scope` 自述 "no flight or G6 equivalence claim" |
| 历史与输入 | 冻结记录 40 项哈希，`historical_and_input_hashes_unchanged: true`、`changes: []` |
| 冻结记录 | `validation/coordination/native-inputs-20260912/current-wrapper-01.json`；驱动冻结 SHA `0f6c7a8caa6b6b885115e76986bceb0ecc07f06050ea78c316d8aa14747c1c68` |

**"哈希不同"的正确表述**：本次实测 `528db324…` ≠ `7da68532…`，大小 `87584` ≠ `87312`。仅记录本次观测；不构成"任何 wrapper 变更都必然产生不同字节"的普遍推断。

### B.3 本次**未覆盖**的范围

| 未覆盖项 | 依据 |
| --- | --- |
| reset / 冷重建周期 | 新证据目录无 `audit.json`、`cold/`、`original/`、`cycle-*.jsonl`；冻结记录写明 100-step check only |
| 新增 terrain 接口 | 探针为 `[0.5]*16` 常量输入；新证据文件中不出现 `terrain` 字样 |
| 新增"已初始化态"语义 | 同上，无对应断言；`9bb11ce` 未被独立核验 |
| G6 / 物理精度 / Full | 冻结记录 `full_or_g6_acceptance: false`；R1 `numerical_failed` 与 5684 失败值原状 |
| 接口/布局全量审查 | 探针只验证 120 维、有限性、时钟 ±1e-8 |

### B.4 仍然未变、不得据本次结果宣称

- **#9 仍 OPEN**，**#26 不因此可关闭**。
- AC5 要求的主代理复核记录、子票→AC 映射表仍缺。
- 不得由本次通过推断物理正确、G6 通过、terrain 接口已验收、或 AC1–AC4 已覆盖。
- 不得用本文件替代 #60 的 `docs/plan/full-acceptance-report.md`。
- 新证据不得写入或覆盖 `validation/codegen-e0-build-short-cycle-01/`、`validation/codegen-e0-lifecycle-01/`、`docs/plan/26-closure-readiness-manifest.json`。

### B.5 当前 wrapper 的独立 native 生命周期（主会话实测，2026-09-12；**非计划**）

`validation/codegen-e0-lifecycle-current-wrapper-01/` 由主会话实际执行，绑定**当前** wrapper（`150ddf3b…` / 4070 B）：

| 项 | 实测值 |
| --- | --- |
| `audit.json` status / schema | `pass` / `wksim.generated-e0-lifecycle.v1`（SHA `0b5d96c97fcba5120213a2143ca641375878140435bc681b58ea3fcef8c5ff29`） |
| 规模 | `ticks_per_cycle=1000`、`cycles=4`、`compared_values=480000`、`clock_tolerance_s=1e-08` |
| 四份 raw | `original/cycle-0..1.jsonl`、`cold/cycle-0..1.jsonl` **实测同为** `0979200da666f80d679203f07c47effd5d7385d3a0ddb1fe2b30e1bbc70b7553` |
| library | `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328` |
| 两次独立子进程 | original `pid=705, pgid=705`；cold `pid=706, pgid=706`；`returncode` 均为 `0` |
| cold 库位置 | `/root/wksim-codegen-e0-cold-907225b3b06c/libwksim_e0.so` |
| 收据 | `validation/coordination/native-inputs-20260912/current-lifecycle-01.json`（`1e28021eaf0f573b3ad3db22d89c58bc89e31da8599b6bd194e49d3e54d80a55`），`inputs_and_history_unchanged: true`（43 项） |
| 边界 | `limitation` = "Independent Linux reconstruction and reset only; no flight or MATLAB numeric oracle" |

**由此新增覆盖**：当前 wrapper 的 cold/reset 生命周期（此前 `validation/codegen-e0-lifecycle-01/` 绑定的是旧 wrapper `3f325678…`/1864 B）。
**仍未覆盖**：terrain 接口、已初始化态语义、G6/物理精度、可选 DLL ABI。逐条映射见 `docs/plan/26-current-source-ac-evidence-20260912.md`。

**外层 shell 收尾噪声（单列）**：全部验证与哈希检查完成后，外层 shell 出现一条多余 CR 命令并 `exit 1`（`carriage-return command not found`）。它发生在 native validator 完成之后，`rerun_required: false`，**native 无需重跑**。

### B.6 本轮决策记录（含 codebuddy 报告处置）

| 项 | 决定 |
| --- | --- |
| 冻结输入 | `tools/validate_generated_e0_lifecycle.py` = `ec883644…` 已主审 + codebuddy 审，**本轮冻结以便提交，不再改** |
| codebuddy **F3**（建议清除 cold 目录） | **不采用**。`/root/wksim-codegen-e0-cold-<uuid>` 是**保留的构建证据**（冷重建产物，其哈希是 AC3 判据的一部分），清除会销毁证据。此处明确声明即可 |
| codebuddy **F1/F2**（错误诊断措辞 / 冗余大小缺项） | 仅记为诊断质量与冗余项；**SHA 门仍在**、不影响判定。记录后后续处理，**本轮不扩大** |
| codebuddy **F4**（测试 docstring） | 本轮**不改**（优先文档、避免更动冻结输入）；若改须先报新 SHA |
| 历史证据 | 不改旧 pin manifest，不使历史看似执行了当前源码 |

---

## C. 边界与命名规则（可核验的政策条目）

这部分是**规则清单**，不是从印象重建的叙述。

### C.1 只读、零改动的证据

| 路径 | 状态 |
| --- | --- |
| `validation/codegen-e0-build-short-cycle-01/` | 只读，逐字节不变 |
| `validation/codegen-e0-lifecycle-01/` | 只读，逐字节不变 |
| `validation/codegen-e0/short-cycle-codegen-01/` | 只读，逐字节不变 |
| `docs/plan/26-closure-readiness-manifest.json` | 只读，逐字节不变 |
| `docs/plan/26-generation-contract.md` | 只读，逐字节不变 |
| `tools/audit_26_closure_readiness.py` | 只读，逐字节不变 |
| `Simulator/wksim_core/model.cpp` | 只读，逐字节不变 |
| 历史被 pin 的 wrapper 原件 `/root/wksim-codegen-e0-build-short-cycle-01/model.cpp`（`3f325678…`，1864 bytes） | 只读，逐字节不变 |

### C.2 命名规则

- 只允许新目录：`validation/codegen-e0-build-current-wrapper-01/`、`validation/codegen-e0-lifecycle-current-wrapper-01/`、`/root/wksim-codegen-e0-build-current-wrapper-01`。
- 不得使用 `short-cycle-01`、`short-cycle-02` 等既有 id；**不得**重用 `/root/wksim-codegen-e0-build-short-cycle-*` 与 `/root/wksim-codegen-e0-cold-*`。
- `--output`（验证器）必须是不存在的新目录；**严禁**写 `validation/codegen-e0-lifecycle-01/`。

### C.3 禁止外推边界

以下推论明确禁止：

1. **不得**声称"当前 wrapper 的冷重核通过 ⇒ #26 可关闭"（#9 仍 OPEN，AC5 复核记录缺失）。
2. **不得**声称"新的 `.so` 通过 ⇒ 物理精度通过 / G6 通过 / R1 改判"。
3. **不得**声称"生命周期通过 ⇒ 模型物理正确"（无 MATLAB 数值 oracle）。
4. **不得**把新证据写入或覆盖历史目录，也不得用新哈希"更新"旧 manifest。
5. **不得**声称"重核通过 ⇒ 已覆盖 terrain 输入 / 已初始化态语义"。
6. **不得**把"编译链接成功"等同于"全部导出/布局与合同一致"。
7. **不得**声称本计划覆盖 #26 的 AC1–AC4。
8. **不得**用本文件替代 #60 的 `docs/plan/full-acceptance-report.md`。

### C.4 本模块的执行边界

本模块（DS-D）只做只读核验、文档与纯行为测试，**不**执行 `.so`/DLL 加载、MATLAB、编译或 native/飞控/ROS/UE 节点。

---

## 13. 准入顺序加固（2026-09-12，本模块实施；经主会话 diff 复审后二次收口）

主会话审读 `run()` 源码并两次复审本模块的 diff，指出顺序与清理缺陷。最终合同：**六源字节必须先全部读入内存并验证哈希、library 身份必须先确认，然后才允许任何快照写入；任何失败都清理自己的快照。**

### 13.1 修复前的实际顺序（首次审读结论）

| # | 原行为 | 问题 |
| --- | --- | --- |
| 1 | `output.mkdir(...)` 在最前 | 读取并验证 manifest **之前**就创建了输出目录 |
| 2 | `assert set(sources)==expected` | 只比较集合 |
| 3 | 仅 `assert len(parents)==1` | **只校验父目录集合，不校验文件名与 key 对应** |
| 4 | 源哈希 `assert` | 在 cold 与 contract 均已创建之后 |

### 13.2 复审指出的缺陷（已全部修复）

| # | 缺陷 | 处置 |
| --- | --- | --- |
| 1 | 已有**空** output 被放行，直到副作用之后 `mkdir(exist_ok=False)` 才失败 | `run()` 拒绝**任何**已存在 output（含空目录、普通文件、symlink），判断在任何 snapshot/copy/compile 之前 |
| 2 | `source_root` 只做词法检查；构建父目录本身若为 symlink 即可逃逸 | 新增 `resolve_build_root()`：先拒 symlink、再要求 `/root` 直接子目录 + 冻结前缀，再 `resolve()` 并要求与词法 root 一致 |
| 3 | 快照 `mkdtemp` 后中途失败不会被清理 | 快照创建后立即进入 `try`，`except BaseException` 中 `shutil.rmtree(snapshot)` 后重抛；只删自己的快照 |
| 4 | manifest 已复制，但 contract 再次对原文件取 SHA，可能标错源 | `load_build_manifest()` 返回 `(manifest, sha_at_read)`；contract 使用该读取时 SHA；快照 manifest 必须与其逐字节一致；原始库亦以读取时字节核验后才写入快照 |
| 5 | **六源核验被移入快照写入之后**（第二轮复审指出） | 拆成 `read_verified_sources()`（全部读入内存、逐源比对哈希、**不写任何字节**）与 `write_snapshot_sources()`（写已核验字节并对副本再哈希）。坏输入因此**零写副作用** |

### 13.3 优化（不写第二套框架）

- 无新框架；沿用原文件既有工具函数。
- `read_verified_sources()` 一次性把六源读入内存并验证；六源总量小，比"边写边验"更简单且满足零写合同。
- `read_regular()` 统一了"非 symlink 普通文件"读取，避免重复判断。
- 删除了原 `verify_source_hashes()`（职责并入读入阶段），未保留并行校验链。

净规模：原始 131 行 → 首次加固 204 行 → 最终 226 行。

### 13.4 最终顺序

只读阶段（零写入）：

1. output 预检：symlink / 已存在（任意类型，含空目录）→ 拒绝。
2. `load_build_manifest()`：symlink、非普通文件、畸形 JSON、非对象根 → 拒绝；绑定读取时字节 SHA。
3. `source_root()` → `resolve_build_root()`：六源精确匹配；绝对 POSIX；无 NUL；basename 必须等于 key；唯一共享父目录；拒 symlink 根与解析逃逸。
4. `read_verified_sources()`：**六源全部读入内存并逐源比对哈希**。
5. `check_library_identity()`：summary 同目录且为普通文件；`library_sha256` 为 64 位 hex；库为普通文件；实测哈希与大小一致；随后按读取时字节复核并留在内存。
6. 冻结 `contract.json` 字典（含读取时 manifest SHA；数值未改）。

副作用阶段：

7. `mkdtemp` 建私有快照 → 复制 manifest 并核对读取时 SHA → `write_snapshot_sources()` 写入已核验字节 → 写入已核验的库字节。
8. `output.mkdir(exist_ok=False)` → 建 cold → 从快照复制 → 编译 → 冷库哈希必须等于原库 → `ldd`。

任意失败：`except BaseException` 删除本次快照后重抛。

### 13.5 明确未改动的契约

编译器 argv、`contract.json` 全部数值门（`ticks=1000`、`dt_s=0.001`、三段输入、`output_count=120`、`clock_absolute_error_s=1e-8`）、数值比较与 `4×1000` 步原门、`audit.json` schema 与字段、冷重建哈希必须等于原库、旧证据与厂商源——全部未改。

### 13.6 纯行为测试

`validation/test_generated_e0_lifecycle_admission.py`，用临时数据与 `subprocess` 替身驱动，不编译、不加载 `.so`、不跑 native、不触 ROS/UE/MATLAB。

| 断言类别 | 覆盖 |
| --- | --- |
| 六源内存核验 | 全部读入并逐源比对；核验阶段**不写任何文件**；哈希不符时快照目录仍为空 |
| 已核验字节 | 核验后改动原文件，快照写入仍为核验时字节 |
| 拒绝 source symlink | 单个源 |
| 拒绝名称不匹配 | key 与 basename 不一致 |
| 拒绝共同父目录逃逸 / 前缀不符 / 非 `/root` 直接子目录 / 不存在 | 单源换父目录；真实但前缀错的目录；嵌套；缺失 |
| 拒绝 symlink 构建根 | 含指向 `/root` 之外 |
| 拒绝哈希不符 | 源哈希；库哈希与 `summary.json` 不符；库大小不符 |
| 拒绝任何已有 output | 空目录、非空目录、普通文件、符号链接 |
| **副作用前拒绝** | `mkdtemp` / `subprocess.run` / `Popen` 替换为抛错替身：库身份与源哈希失败时**从未创建快照**；输出已存在时亦然 |
| 失败清理 | 在快照阶段注入 `OSError`，断言快照目录已被删除 |
| 读取时身份绑定 | manifest 读取后改动文件不改变已绑定 SHA |
| 成功路径 | 保留恰好一个快照且含 `libwksim_e0.so`；编译器 argv、`contract.json` 六项数值、`audit.json` 的 `4×1000` 与 `compared_values` 未改 |

> **运行说明（重要）**：该验证器与这套测试**只能在 Linux 上运行**。`run()` 首行即 `if sys.platform!='linux': raise ValueError(...)`，且 `/root` 必须是真实绝对路径（Windows 上 `Path('/root/...')` 不是绝对路径）。不要把 PowerShell 命令当作可直接在 Windows 运行。
