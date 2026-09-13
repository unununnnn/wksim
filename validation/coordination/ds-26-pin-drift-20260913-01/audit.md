# #26 pin-drift 裁定 — 只读 G4 复核

- 工作类别：`new-development` / 只读 G4 #26 pin-drift adjudication（**非**历史对照检出）
- 仓库：`C:/Users/PC/Documents/odid编译/wksim`，remote `origin = https://github.com/unununnnn/wksim.git`
- 起始 HEAD：`100ef1aafcc19c006d93eeb16b0c41e2352cdee6`
- 复核期间 HEAD 推进至：`1a8d5083b70461e6e6984566f7298c993f0c5392`（期间新增 3 个提交：`34d6076 Pin accepted native load sites in core audit`、`a9d9ccc Record current G0-G5 closure frontier`、`1a8d508 Record expanded DLL ABI evidence`；`100ef1a…` 是当前 HEAD 的祖先）
- **稳定性已核**：`Simulator/wksim_core/model.cpp`、`docs/plan/26-closure-readiness-manifest.json`、`tools/audit_26_closure_readiness.py` 三者的 git blob 在 `100ef1a`/`34d6076`/`HEAD` 三个点上**完全相同**（`4975598d95f8` / `af7fdfa6c9b2` / `11eec11f9889`），工作树与 HEAD 亦无差异；5 条 violations 在新 HEAD 上原样复现。
- 两个 HEAD 均满足 `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit `0`
- 本模块写入范围：`validation/coordination/ds-26-pin-drift-20260913-01/`（独占）
- **未修改**：`docs/plan/26-closure-readiness-manifest.json`、`tools/audit_26_closure_readiness.py`、`validation/codegen-e0*/**`、`Simulator/wksim_core/model.cpp`、`validation/test_audit_26_closure_readiness.py`、issue、共享账本
- **未执行**：native、编译、ROS、飞控、模型、UE、MATLAB。全部结论由只读读取、`git` 只读 plumbing 与纯 Python 哈希重算得出。

---

## 0. 执行摘要

`tools/audit_26_closure_readiness.py` 当前报告 `status = not_ready`，共 **5 条 violations**。逐条裁定后：

| # | 当前 violation | 裁定 | 级别 |
| --- | --- | --- | --- |
| 1 | `build manifest.staged_sources.model.cpp size drifted: expected 1864, observed 4070` | **审计器误分类**（历史 pin 被按"当前源码"检验）；pin 本身**正确且可复核** | P1 |
| 2 | `lifecycle cold_library cannot be mapped on this host` | **环境分类项误报**（Windows 宿主上的 `/root` 路径） | P2 |
| 3 | `lifecycle cold probe cannot be mapped on this host` | 同 #2 | P2 |
| 4 | `build output library cannot be mapped on this host` | 同 #2 | P2 |
| 5 | `vendor artifacts tracked in repository: [...5 paths...]` | **审计器误分类**：33 条 tracked 路径**全部**是按文件名命中的 WSL precheck 回执，无一条携带厂商字节 | P1 |

**核心结论**：`not_ready` 目前**不是**由任何实质性的 pin 漂移或厂商材料违规造成的。5 条 violations 中 0 条是真实漂移、0 条是真实厂商材料。经纠正后，唯一仍然成立的机器可判定阻塞项只有 manifest 自己记录的**形式依赖 `#9` 仍 OPEN**，即状态本应为 `ready_blocked_by_formal_dependency`。

**因此不需要重写任何历史 pin。** 被 pin 的 1864 B wrapper 字节虽**不在 git 对象库中**（`3f325678…` 在 wrapper 路径上从未被提交），但其字节被**逐字节保存**在一条 tracked 冻结快照中并已由本模块重算确认 —— pin 认证的是真实归档材料。

同时存在一项**真实的未验收实现**（P0，形式为"未验收实现"而非漂移）：当前 tracked wrapper 新增的 terrain 输入接口与"已初始态"语义，已在仓库内被明确记录为**未被任何探针驱动、未被独立核验**（详见 §4.2）。该状态由 manifest 的"当前源码"证据链如实声明，但审计器**没有**检查它。

---

## 1. 复现命令（纯 Python，无第三方依赖）

```powershell
# 1) 祖先与 HEAD
git -C . rev-parse HEAD
git -C . merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD; $LASTEXITCODE   # 期望 0

# 2) 当前审计（用于记录"待纠正"的 5 条 violations）
python tools/audit_26_closure_readiness.py | Select-Object -Last 30; $LASTEXITCODE                # 期望 exit 2 / not_ready

# 3) 本模块独立重算（只读；不写任何 tracked 路径）
python validation/coordination/ds-26-pin-drift-20260913-01/recheck_26_pin_drift.py
python validation/coordination/ds-26-pin-drift-20260913-01/summarize_recheck.py
```

`recheck_26_pin_drift.py` 的判据全部来自重算：manifest 六个 pin 逐字节重算、`audit.json` 与 manifest `requirements` 交叉比对、每个 `build-manifest.json` 的 `model.cpp` pin 与当前 tracked 源比对、用 `git ls-files` 枚举**全部** tracked `model.cpp` 快照并逐字节重算以判定历史字节是否仍留存、以及把 33 条厂商规则命中项逐条做**内容分类**。

---

## 2. 稳定哈希（SHA256）

### 2.1 被裁定对象

| 角色 | 值 |
| --- | --- |
| 起始 HEAD | `100ef1aafcc19c006d93eeb16b0c41e2352cdee6` |
| 复核期 HEAD | `1a8d5083b70461e6e6984566f7298c993f0c5392` |
| 被裁定三物件在三个 HEAD 上的 blob | wrapper `4975598d95f8` / manifest `af7fdfa6c9b2` / audit tool `11eec11f9889`（三处相同） |
| 架构连续性 pin | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`（确为祖先） |
| 当前 tracked wrapper 文件 SHA256 | `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290`（4070 B） |
| 当前 wrapper git blob | `4975598d95f8de7cd8caee2d68a1d51511d32f45` |
| 历史被 pin wrapper SHA256 | `3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c`（1864 B） |
| **历史 wrapper 字节的留存副本** | `validation/lunar-20-epoch-1/case/run/epochs/2a8d5df1dd4244c3868dc7f38e85a369/source/Simulator/wksim_core/model.cpp`（tracked，重算 = `3f325678…`，1864 B） |
| 当前 wrapper 构建证据 | `validation/codegen-e0-build-current-wrapper-01/build-manifest.json` = `434d1745924f9b0a4910a034e1b4847476e02ccde1c7b06f020087880c1f9226` |
| 当前 wrapper 生命周期证据 | `validation/codegen-e0-lifecycle-current-wrapper-01/audit.json` = `0b5d96c97fcba5120213a2143ca641375878140435bc681b58ea3fcef8c5ff29` |
| 当前 wrapper 当前库 | `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328`（87584 B） |
| manifest 六个 pin | 全部完好（逐条见 §5） |

### 2.2 wrapper 字节在 git 中的可复现性（决定纠正方案的关键事实）

| 提交 | 路径 blob | 大小 |
| --- | --- | --- |
| `55773c5`（2026-09-06 导入） | `e0e96466a407d49572a8f3ec911515b4e855147f` | 1864 B |
| `f9a34f8`（2026-09-11 Expose same-source terrain input） | `b121f1e15e4b377b088eadb5478185034c42735f` | 3305 B |
| `9bb11ce`（2026-09-11 Expose initialized model state） | `4975598d95f8de7cd8caee2d68a1d51511d32f45` | 4070 B |
| `HEAD` | `4975598d95f8de7cd8caee2d68a1d51511d32f45` | 4070 B |

`git cat-file -e 3f325678…` → `fatal: Not a valid object name`（exit 128）。跨**全部 refs** 检索 wrapper 路径 blob 亦无命中。

**解读**：被 pin 的 1864 B 版本与 `55773c5` 所提交的 1864 B 版本**大小相同但字节不同**。也就是说，构建当日 wrapper 路径上放着的是一个**未被提交的 1864 B 变体**，此后被 `f9a34f8`/`9bb11ce` 覆盖，故该 SHA256 永远不可能作为 git 对象存在。这是"pin 指向真实但未入库的构建输入"，**不是"pin 写错"**。其字节由 tracked 冻结快照留存，因此 pin 仍可被复核。

---

## 3. 逐条裁定

### 3.1 violation #1 —— `model.cpp` "size drifted"

**裁定：审计器误分类（P1）。不是错误 pin，不是未验收实现。**

依据链：

1. `validation/codegen-e0-build-short-cycle-01/build-manifest.json` 的 `staged_sources.model.cpp` = `3f325678…` / 1864 B，其 `source_path` 为 `…/wksim/Simulator/wksim_core/model.cpp`。
2. `tools/audit_26_closure_readiness.py:327-346`（`_check_source_actual`）把该 `source_path` 映射回仓库相对路径，命中 `ALLOWED_REPO_WRAPPERS`（`:60`），随后在 `:340-346` 调用 `_actual_file`，以 **pin 的 sha/size** 去校验**今天的** `Simulator/wksim_core/model.cpp`。
3. 今天的文件是 `150ddf3b…` / 4070 B → 必然产生 `size drifted` + `hash drifted`。**该检查把"历史证据绑定历史源码"当成"当前源码漂移"。**
4. pin 自身在其自证链内**完全自洽**：`validation/codegen-e0-lifecycle-01/audit.json` 的 `source_sha256["model.cpp"]` = `3f325678…`，与 manifest `requirements.source_sha256` 相等，且该 `audit.json` 的 SHA256 `3d5c7896de10d10521ff4a1881eaffc8c96e73b196be72f9a044f2fc1aed346d` 与 manifest 的 `matlab_free_lifecycle` pin 相等。**旧链验证旧链，成立。**
5. 漂移来源是两个功能性提交（`f9a34f8`、`9bb11ce`），二者均**晚于**历史构建，且**已被**当前源码证据链重新绑定：`validation/codegen-e0-build-current-wrapper-01/build-manifest.json` 绑定 `150ddf3b…` / 4070 B，`validation/codegen-e0-lifecycle-current-wrapper-01/audit.json` 绑定同一 wrapper 与库 `528db324…`，`docs/plan/29-terrain-evidence-manifest.json:111` 亦绑定 `150ddf3b…`。
6. 仓库内已有具名文档逐字记录这一区别：`docs/plan/26-current-wrapper-recheck-plan.md:61-64`、`docs/plan/26-current-source-ac-evidence-20260912.md:89`，且 `26-current-wrapper-recheck-plan.md:103` **明令**"新证据不得写入或覆盖 `validation/codegen-e0-build-short-cycle-01/`、`validation/codegen-e0-lifecycle-01/`、`docs/plan/26-closure-readiness-manifest.json`"。

**结论**：现行 pin 是**正确 pin**，且是**已接受的架构演进**（新增 terrain 与已初始态接口）之后**有意的历史留存**。纠正方向是修审计器，而**不是**改 pin。

### 3.2 violations #2–#4 —— `cannot be mapped on this host`

**裁定：环境分类项误报（P2）。**

`/root/wksim-codegen-e0-cold-c96e30e01ec6/libwksim_e0.so`、`/root/wksim-codegen-e0-build-short-cycle-01/libwksim_e0.so` 是 WSL Ubuntu22.04 内的构建/冷重建产物路径。`tools/audit_26_closure_readiness.py:660-676`（`_as_host_path`）在 `os.name == 'nt'` 时对 `/` 起始路径返回 `None`，`:293-295` 随即计入 violation。证据文件从未声称这些路径在 Windows 宿主上可解析；`docs/plan/26-current-wrapper-recheck-plan.md:36-37` 亦明载该验证器"只能在 Linux 上运行"。此为宿主边界，非证据缺陷。

### 3.3 violation #5 —— "vendor artifacts tracked in repository"

**裁定：审计器误分类（P1）。真实厂商材料数量 = 0。**

`tools/audit_26_closure_readiness.py:932`：

```python
vendor_offenders = [name for name in tracked if re.search(r"(?:\.dll$|\.zip$|rflysim)", name, re.IGNORECASE)]
```

该正则的 `rflysim` 分支以 `re.search`（**非锚定**）作用于**路径文本**，因此命中一切路径中含 `rflysim` 的 tracked 文件。而本仓的 WSL 宿主探测回执正是以发行版名 `RflySim-20.04` 命名。

本模块重算结果：

| 项 | 值 |
| --- | --- |
| 正则命中的 tracked 路径数 | **33** |
| 内容分类（逐条读字节） | `wsl-precheck-receipt-empty`（JSON，`found: []`）与 `text-precheck-note`（`.txt`，同格式 + 一条 systemd 警告） |
| `found` 非空的回执数 | **0** |
| tracked `.dll` / `.zip` 文件数 | **0** |
| 真实厂商材料数 | **0** |

回执内容示例（`validation/coordination/native-release-wait-bench-20260913-02/precheck-RflySim-20.04.json`）：

```json
{"checked_unix": 1789257110.558233, "distro": "RflySim-20.04", "boot_id": "d2131159-199f-4795-9a65-cbd9846b0155", "uptime": "301.70 5984.13", "found": []}
```

即：**"在 RflySim-20.04 发行版中没有发现运行中的进程"**的探测回执。`found: []` 恰恰是"未发现"的否定证据，被规则读成了肯定的违规。

补充：manifest 的 `vendor_materials_controlled.ac` 写的是"厂商材料留在受控本地来源；不得提交授权不明生成源码"，`:135` 的 `rule` 写的是"不得有 tracked 的 vendor DLL/ZIP 或 pin 构建的生成/私有源码"。文件名命中的回执**两者都不违反**。同一函数中针对生成源码的两条真实检查（`:935-942` pinned generated root、`:950-957` private/generated source tracked）**未报告任何违规** —— 即 AC4 的实质要求当前**是**满足的。

### 3.4 未验收实现（P0）—— 当前 wrapper 的两个新增接口

**裁定：未验收实现。** 这一项**不是** pin 漂移，也**不是**审计器误报；它是 tracker 内**已如实声明**但审计器**未检查**的覆盖缺口。

| 接口 | 来源提交 | 当前状态 |
| --- | --- | --- |
| 同源 terrain 输入（`wk_model_step_with_terrain`，15 维地形） | `f9a34f8` | 实现已 tracked；**未被任何探针驱动** |
| 已初始化态语义（`wk_model_initial_state`） | `9bb11ce` | 实现已 tracked；**无对应断言** |

仓库自证（`docs/plan/26-current-source-ac-evidence-20260912.md:172-176`、`26-current-wrapper-recheck-plan.md:92-93`）：探针为 `[0.5]*16` 常量输入，"证据文件中不出现 `terrain` 字样"，`9bb11ce`"未被独立核验"。当前 wrapper 的 100 步探针与 4×1000 生命周期**未覆盖**这两个接口。

`Simulator/wksim_core/model.cpp:26-35, 38-42, 73-75, 88-93` 确实实现了二者并含参数校验，但"能编译链接"与"接口/布局与合同一致"被 `26-current-wrapper-recheck-plan.md:169` 明确列为**不得等同**。

**因此**：这两个接口处于"已实现、未验收"状态，需要单独验收子票；在它们被独立核验前，不得据当前 wrapper 的构建/生命周期通过推断其已验收。

---

## 4. 纠正方案（最小、不覆盖历史原件）

### 4.1 设计约束

1. **不**重写 `docs/plan/26-closure-readiness-manifest.json`，**不**把 `150ddf3b…` 写进历史 pin（`26-current-wrapper-recheck-plan.md:167` 明令禁止）。
2. **不**删除或覆盖 `validation/codegen-e0-build-short-cycle-01/`、`validation/codegen-e0-lifecycle-01/`（`:145-146` 只读、逐字节不变）。
3. **不**改 `Simulator/wksim_core/model.cpp`。
4. 关键实现细节：审计器**已有**一条跨链绑定（`tools/audit_26_closure_readiness.py:884-889`）要求 `build.staged_sources[*].sha256 == audit.source_sha256`。因此任何"把历史 wrapper 重新绑定到今天的源码"的改法都会在 `:888` 自相矛盾。**patch 不能改 wrapper 的绑定值，只能改"用哪份字节去复核该值"。**

### 4.2 P1-A 修正 wrapper provenance 绑定

新增一份**新目录内的**历史证据宣告（不改任何既有文件）：

```
validation/coordination/ds-26-pin-drift-20260913-01/historical-wrapper-identities.json
```

内容（本模块已随交付提供该文件，供 patch 采用）：

- `schema = wksim.26-historical-wrapper-identities.v1`
- 逐条列出被 pin 的历史 wrapper 身份：`sha256`、`size_bytes`、`pinned_by_build_ids`、`archived_repo_path`（现存 tracked 快照）、`status = "historical_superseded_not_drift"`、`superseded_by_sha256`、`commissioned_current_evidence`。
- 本 pin 对应的条目：`3f325678…` / 1864 B，归档于 `validation/lunar-20-epoch-1/case/run/epochs/2a8d5df1dd4244c3868dc7f38e85a369/source/Simulator/wksim_core/model.cpp`，被 `current-wrapper-01`（`150ddf3b…` / 4070 B）取代，当前证据为 `validation/codegen-e0-build-current-wrapper-01/`。

`tools/audit_26_closure_readiness.py` 精确 patch 边界：

| 位置 | 现状 | 改动 |
| --- | --- | --- |
| `:59-61` | `ALLOWED_REPO_WRAPPERS = {"Simulator/wksim_core/model.cpp": "generated-model-wrapper"}` | 保持；**新增** `DEFAULT_HISTORICAL_IDENTITIES` 指向上述新文件路径常量 |
| `:235-258` `_secure_file` | 已拒 symlink/reparse/逃逸 | 复用，用于安全解析归档快照路径 |
| `:327-346` `_check_source_actual` | wrapper 分支只做 `repo_rel != "Simulator/wksim_core/model.cpp"` 拒绝 + `_actual_file(现状路径)` | wrapper 分支改为：**先**在历史身份表中查 `item["sha256"]`；**命中**则把待复核路径解析为 `identity["archived_repo_path"]`（经 `_secure_file` 校验存在性、symlink、repo 边界）并对该路径做 `_actual_file(sha256=item["sha256"], size_bytes=item["size_bytes"])`；**未命中**则维持现状（当前源码必须逐字节等于 pin）。 |
| `:700-753` `_check_build_manifest` | `:744-753` 用 `_repo_relative_from_source` + `ALLOWED_REPO_WRAPPERS` 判仓库来源 | 增加一条：若 `item["sha256"]` 命中历史身份表，要求 `archived_repo_path` **确实 tracked 且存在**（沿用 `:750` 的 `is_file()` 风格），否则 fail-closed。 |
| `:884-889` `_check_lifecycle_evidence` | 用 `build.staged_sources` 的哈希与 `audit.source_sha256` 交叉绑定 | **不改数值比较**；仅在解析 wrapper 源文件时复用同一历史身份分派，使 `:888` 的两个哈希（同为 `3f325678…`）在归档副本上同时成立。 |

**fail-closed 性质**：历史身份表是**枚举式**的，只含 `3f325678…` 一个 digest。任何**新的、未被宣告的** wrapper 变更仍会在 `:333-346` 失败并产生 violation —— 即"未验收的实现改动"依然被拦下。

**可选、独立的第二段（P2）**：在 `:802-918` `_check_lifecycle_evidence` 与 `:265-282` `_actual_file` 的调用点，把 `_as_host_path` 返回 `None` 的 `/root/...` Linux-only 路径归入单独的 `"host_bounded"` 列表而非 `violations`，并在报告顶层输出 `host_bounded[]`，使"宿主不可解析"与"证据漂移"在机器可读层面分离。

### 4.3 P1-B 修正厂商材料分类

`tools/audit_26_closure_readiness.py:932` 精确替换为"**先判扩展名、再判内容**"：

- `.dll` / `.zip`：**保持**为违规。
- 其余：不再对路径文本匹配 `rflysim`。改为**内容判定** —— 仅当文件为二进制（含 NUL 或非 UTF-8 解码失败）或含厂商材料magic/签名时才违规。
- 明确**允许** `validation/coordination/**` 下的 WSL 宿主探测回执：其 schema 为 `{checked_unix, distro, boot_id, uptime, found}`，且 `found == []` 表示"未发现"。允许这类回执**不**削弱 AC4 —— 同一函数 `:935-942`（pinned generated root）与 `:950-957`（private/generated source tracked）才是 AC4 的实质判据，二者当前均无违规。

### 4.4 测试边界（与 patch 同时落地，本模块不执行）

`validation/test_audit_26_closure_readiness.py` 需同步更新，因为它们把当前（有缺陷的）行为**固化**为断言：

| 位置 | 现状 | 需要 |
| --- | --- | --- |
| `:291-300` `test_private_generated_source_and_vendor_artifact_cannot_be_tracked` | 以 `vendor.dll`（真 `.dll`）构造违规 | **保持**（真 DLL 仍须被拒）；建议**新增**用例：`precheck-RflySim-20.04.json` 形式回执**不得**被判违规 |
| `:471-484` `RealRepositoryTests` | `test_real_historical_evidence_is_conservatively_not_ready` 断言 `violations` 非空且 `status == not_ready`；`test_cli_exit_codes` 断言 exit `2` | patch 后真实仓库**应当**不再产生 wrapper/vendor 违规，故两条断言必须改为"violations 仅剩已宣告的宿主边界项"与对应退出码（`main():999` 在无违规时返回 `0`） |

注意 `:41-99` 的 `_fixture` 会把**当前** wrapper 复制进临时仓库并按当前字节重写 pin，因此 fixture 类测试自洽、不受本问题影响；受影响的是 `RealRepositoryTests`。

### 4.5 不做什么

- **不**把 `150ddf3b…` 写进 `26-closure-readiness-manifest.json` 的任何 pin。
- **不**删除 `/root/...` 相关历史 JSON，**不**删除 33 条宿主回执。
- **不**因本次纠正而宣称 #26 可关闭：#9 仍 OPEN，且 AC5 的"主代理复核记录"仍缺（`docs/plan/26-current-source-ac-evidence-20260912.md:113`）。审计器的 AC5 检查（`:143-150`）只验证 `delivery_identity` pin，**不**检查复核记录是否存在，补 patch 时不得据此提升结论。
- **不**由当前 wrapper 的构建/生命周期通过推断 terrain 接口或已初始态语义已验收（§3.4）。

---

## 5. manifest 六个 pin 的独立重算（全部完好）

| AC | 路径 | 重算 SHA256 | 结果 |
| --- | --- | --- | --- |
| `source_chain` | `docs/2026-09-10-generated-e0-lifecycle.md` | `60a223620e7fc96b519bfa383fd1712c40386b99ed5812f6d2262c3b644a3d7a` | 一致 |
| `source_chain` | `validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json` | `85c40213cec0f349d36664c5621bb53c46ad96f9756cdd4eaa2bb97a7b2acc67` | 一致 |
| `matlab_license_actual_checkout` | `validation/codegen-e0/short-cycle-codegen-01/codegen-report.json` | `e5f32bd2890137591b61eba72fe0b21893fef578fd0a57094baf8fe92398f822` | 一致 |
| `matlab_free_lifecycle` | `validation/codegen-e0-lifecycle-01/audit.json` | `3d5c7896de10d10521ff4a1881eaffc8c96e73b196be72f9a044f2fc1aed346d` | 一致 |
| `vendor_materials_controlled` | `validation/codegen-e0/short-cycle-codegen-01/summary.json` | `42bc11a2a55fc26542cb52d34fc22d7ae8b3c6fc66deec19708aa232eb910f7c` | 一致 |
| `delivery_identity` | `validation/codegen-e0-build-short-cycle-01/build-manifest.json` | `0669730aeff54012e70c55e8fc1d103cfeb00cc33ec5b3147144df847fc7aa1c` | 一致 |

生命周期交叉绑定亦全部成立：`audit.json.library_sha256 == requirements.library_sha256`、`source_sha256` 相等、`raw_sha256` 相等，`status = pass`，四份 raw 同为 `0979200da666f80d679203f07c47effd5d7385d3a0ddb1fe2b30e1bbc70b7553`。

---

## 6. 残余风险与未决项

| 项 | 说明 | 归属 |
| --- | --- | --- |
| 历史 wrapper 字节**不在 git 对象库** | `3f325678…` 在 wrapper 路径从未提交；仅靠一条 tracked 冻结快照（`validation/lunar-20-epoch-1/...`）留存。其余同字节副本（如 `validation/quad-parameters-native-20260909-b/reviewed-source/model.cpp`）**未被跟踪**。若该唯一 tracked 副本被删除，pin 将不可复核。 | 建议在 patch 中要求 `archived_repo_path` 存在性 fail-closed（§4.2） |
| `Simulator/wksim_core/model_parameters.py:25` 与 `Simulator/wksim_core/motor_efficiency_model.py:68,114` 硬编码旧 `WRAPPER_HASH = 3f325678…` | 该常量指向**不再存在于 canonical 路径**的字节；任何调用方对当前 `Simulator/wksim_core/model.cpp` 直接比对都会失败。`model_parameters.py:156` 与 `motor_efficiency_model.py:68,114` 均含此比对。本模块**未**运行这些脚本，故不断言其当前可用性，仅记录该常量与当前 tracked 源不一致。 | 独立于 #26 的接口/导入器问题（`26-generation-contract.md §3` 提到的导入器缺口） |
| terrain / 已初始态语义未验收 | 见 §3.4 | 需单独验收子票 |
| HEAD 在本模块复核期间被推进 | `100ef1a…` → `34d6076…`；`100ef1a…` 是新 HEAD 的祖先，wrapper/manifest/audit 三者在两个 HEAD 上逐字节一致，故 §2–§5 结论对二者同样成立 | 并发写入者；本模块未与之冲突 |

---

## 7. 结论

1. `tools/audit_26_closure_readiness.py` 报出的 5 条 violations 中，**0 条是真实 pin 漂移、0 条是真实厂商材料**：1 条是历史 pin 被按当前源码检验（P1），3 条是 Windows 宿主无法解析 WSL `/root` 路径（P2），1 条是文件名正则误判 WSL 探测回执（P1）。
2. 被质疑的 `model.cpp` pin 是**正确 pin**：它认证的是**真实存在、未经入库**的 1864 B 构建输入，其字节至今被 tracked 快照逐字节保存，且其旧证据链内部自洽。**不得**改写该 pin 以迁就当前源码。
3. 当前 `150ddf3b…` / 4070 B wrapper **已由独立委任的证据链**（构建 + 4×1000 生命周期 + `#29` terrain manifest）绑定，因此不构成"未验收的源码变更"；但该 wrapper 的**两个新增接口**确属**未验收实现**（P0，见 §3.4）。
4. 纠正方向是**修改审计器的分类与绑定**（§4.2、§4.3）并同步更新固化旧行为的测试（§4.4），**不触碰**任何历史原件。纠正后 `not_ready` 的真实来源将只剩形式依赖 `#9`。
5. 本模块只做了只读核验与上列文档/脚本写入，**未**修改 manifest、工具、测试、issue、共享账本，**未**执行 native/编译/ROS/飞控/模型/UE/MATLAB。
