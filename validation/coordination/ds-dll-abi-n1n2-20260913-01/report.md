# #9 DLL/模型插件 ABI 证据：n1+n2 只读取证（e0/e1 模板 DLL 身份与消费端逐行绑定）

- `checked_at`: `2026-09-13T22:28:54+09:00`（`evidence.json` 内记录的构建时刻）
- 工作类别：`historical-material/read-only ABI evidence acquisition`。**不是**新架构实现、不是 ABI 批准、不是兼容性验收。
- 承接：`validation/coordination/ds-dll-abi-evidence-20260913-01/`（已完成，本次**只读**，未修改任何字节）。本次只完成其 `n1` + `n2`。
- 交付目录（独占写入）：`validation/coordination/ds-dll-abi-n1n2-20260913-01/`
- 机器可读证据：[evidence.json](evidence.json)，SHA256 `01a5c15b429cf46df8f252e62104c5d31389329cd7e5ed2ba71d8ddbd26862dc`
- 原始产物：[raw/n1-pe-templates.json](raw/n1-pe-templates.json)、[raw/n2-consumer-refs.json](raw/n2-consumer-refs.json)
- 只读脚本：`n1_pe_templates_readonly.py`、`n2_consumer_refs_readonly.py`、`build_evidence.py`
- `*.txt` 行尾冻结由 `.gitattributes`（`* -text`）保证，记录哈希不随 CRLF 检出漂移。

---

## 1. 开工核验（实际执行）

| 项 | 值 |
| --- | --- |
| 实际 cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| 分支 | `main` |
| 派发时 HEAD | `0239f0e459bd8f5d7cdc6c25c0c6aa6687ead54f` |
| 交付时 HEAD | `33c2b06e8794ad865a25b307852d08d4c0845a26` |
| 期间 HEAD 变动 | 两次对端提交：`09105fa`（`Record MIXED hook and DLL ABI audits`，首次把**前置审计** `ds-dll-abi-evidence-20260913-01/`、`ds-perf-mixed-hook-audit-20260913-01/` 等录入仓库）→ `33c2b06`（`Reject perf diagnostics from formal MIXED evidence`，仅改 `Simulator/wksim_runtime/joint_profile.py` 与两份测试）。两者**均未触及**本次任何证据输入。 |
| 架构祖先检查 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → 退出码 **0**（派发时与交付时各一次） |
| 证据输入漂移 | **0**。消费端 `DllSimCtrlAPI.py` 实读 SHA256 `0a2a30e9…` 与前置记录一致；前置摘录 `sdk-wrapper-evidence.json` 实读 `bc0b07ab…` 与前置记录一致；HEAD 推进后在 `33c2b06` 上**重跑了全部三步**。 |
| PE 生产者 | 复用仓库既有 `work/coptersim-compat-20260905/inspect_pe.py` 的 `inspect_pe.inspect(path)`（未修改，实读 SHA256 记于 evidence.json），`pefile fast_load`，**不执行**目标 |

**禁止项遵守**：未加载/映射/执行任何 DLL、模型或 EXE；未反汇编、未逆向、未做类型恢复；未复制或发布任何厂商二进制或源码（仅记录元数据与单行文本引用）；未执行 native/构建/ROS/飞控/模型/UE/MATLAB；未修改任何 Issue；未写共享账本或 adapter；**未修改任何既有文件**。`.bat` 一律**只作为文本读取，未执行**。`python -B` + `PYTHONDONTWRITEBYTECODE=1`，仓库内未产生 `__pycache__`。

---

## 2. n1：e0/e1 模板 DLL 与同名二进制只读身份盘点

### 2.1 已命名目标（补齐 path/size/SHA/machine/导出名）

| 目标 | 路径 | 大小 | SHA256 | machine | Dll* 导出 | 输出名族 |
| --- | --- | --- | --- | --- | --- | --- |
| **e0 模板** | `…/1.BasicExps/e0_MinModelTemp/Exp1_MinModelTemp.dll` | 235520 | `30747a8d47ca76ed3a2c751eac212102dde6a3ab4b29ba8eaae5926d416ca91b` ✅与记录一致 | `0x8664` | 12 | 现代 `*30d/*60d` |
| **e1 模板** | `…/1.BasicExps/e1_MinModelTempLib/Exp1_MinModelTemp.dll` | **242176** | **`c2fbfd4dc3a6338bcd040e59960af0c4c8c0925a0c583c4d9792e342d9558000`（首次记录）** | `0x8664` | 12 | 现代 `*30d/*60d` |
| 部署副本 | `…/CopterSim/external/model/Exp1_MinModelTemp.dll` | 230912 | `8134aab646adda098b7c98a4daa17278dbed7a626a1811e18ed1a88288fb6a46` ✅与记录一致 | `0x8664` | 10 | **旧输出名族** |
| 消费端硬编码目标 | `…/CopterSim/external/model/MulticopterNOpx4.dll` | 173568 | `0179c58f14f8140302c1ec1a36ae455e88146c64099be1cd6a633cb174afe7e8`（首次记录） | `0x8664` | 14 | 现代（仅 `…60d`） |

e0 与 e1 模板的 **12 个 Dll\* 导出名集合完全相同**（`DllDestroyModel, DllGetGpsPos, DllGetStep0, DllInitGpsPos, DllInitPosAngState, DllInputPWMs, DllReInitModel, DllTerrainIn15d, DlloutHILGPS30d, DlloutHILSensor30d, DlloutVehileInfo60d, Dllstep`），但大小/哈希不同（差 6656 B）。**导出名集合不能作为二进制的身份判据。** 四个目标均另导出修饰名 `?DllCreatModel@@YAXXZ`，均**无**未修饰 `DllCreatModel`。

### 2.2 同名枚举：歧义不是"两个二进制"，而是 11 个

在 `E:/rflysimtools` 全树按文件名 `Exp1_MinModelTemp.dll` 枚举：**12 份拷贝 → 11 个互异二进制 → 7 个互异导出名集合 → 2 个输出名族**。

```
legacy-only (1): 8134aab6… (230912, 部署副本)
modern-only (11): 0179c58f… MulticopterNOpx4.dll (173568) / 2b152593… DynModiParams (227328)
                  30747a8d… e0 模板 (235520) / 45fd6307… FaultInParams×2 (226304)
                  63726f6d… e2_DLL-Load (242176) / 8bcde46c… sendSILIntDouble (242176)
                  c2fbfd4d… e1 模板 (242176) / d08b35d9… inCollision20d (232448)
                  d17b1c8e… initParams/Python (244224) / db33543c… sendInDoubCtrls (224768)
                  db5add3a… initParams/Matlab (225792)
both families:   （空）
```

新增的 10 个二进制此前**从未被盘点**（前置的 16-DLL 清单只含部署副本）。加上前置 16 个，本次口径下的**并集为 26 个互异二进制**。

### 2.3 横切复核（对本次 12 个二进制全部成立）

`machine` 全为 `0x8664`；全部无 CLR 目录；静态导入**全部且仅** `KERNEL32.dll`；`version_strings` **全为空**；全部导出修饰 `?DllCreatModel@@YAXXZ`、全部无未修饰 `DllCreatModel`。→ 先前 G1/G2/G8 的结论在新增 10 个二进制上**继续成立**。

### 2.4 交付部署机制（新证据，仍未执行任何 `.bat`）

每个实验批处理声明**自己的同胞** DLL 并复制到模型目录后交给 CopterSim：

- `e0_MinModelTemp/Exp1_MinModelTemp_SITL.bat`：`27 set DLLModel=Exp1_MinModelTemp`；`43-44 if exist "%~dp0%DLLModel%.dll" ( copy /Y … "%PSP_PATH%\CopterSim\external\model\%DLLModel%.dll" )`
- 被引样本身的 `CopterSimDllSILRun.bat`：`27 set DLLModel=MulticopterNOpx4`；`43-44` 同为复制；`142 start /realtime CopterSim.exe 1 … %DLLModel% …`

即：**实验加载的是该实验目录自己的同胞二进制**，不是全局择一。残余未解：当前部署的 `8134aab6…`（旧族）在整棵树中**没有任何同胞副本与之哈希相同**，其来源无记录。

---

## 3. n2：消费端精确行号绑定

消费端 `E:/rflysimtools/RflySimAPIs/RflySimSDK/ctrl/DllSimCtrlAPI.py`，2103 行，SHA256 `0a2a30e9fe…`（与前置记录一致）。前置已记录的 1234–1307 摘录**经逐行比对与新读完全一致**（`fresh_reread_equals_recorded = true`，块哈希记于 evidence.json），因此本页**不再重复复制**该段厂商文本，只补相邻范围。

### 3.1 逐符号绑定（导出名 ↔ 声明 ↔ 实际生产端）

| 消费端符号 | 声明行（argtypes / restype） | 生效守卫 | 实际调用/引用行 | 26 并集中生产端数 |
| --- | --- | --- | --- | --- |
| `DllInputSILs` | `c_int[8], c_float[20]` @1230-1233 | 同名 | 1817-1834，1740/1756，2045/2055/2069/2082/2093 | 1 |
| `DllInputColls` | `c_double[20]` @1237-1239 **再** `c_float[20]` @1294-1296 | 同名 | 1842-1849（建 `c_float` @1847）、1952-1959（@1957）、1788 | 1 |
| `DllInitGpsPos` | `c_double[3]` @1243-1245 | 同名 | 1870-1877，1373 | 12 |
| **`DllInitPosAngState`** | `c_double[3],c_double[3]` @1249-1252 **与** @1256-1259 —— **两块都挂在 `DllInitPosAngStat` 守卫下，永不可达** | **异名（缺陷）** | 1884-1894（守卫写对）、1374 | 12 |
| `DllInputDoubCtrls` | `c_double[28]` @1263-1265 | 同名 | 1900-1908，1741、1757，2043/2053/2067/2080/2091 | **0** |
| `DllinSIL28d` | `c_double[28]` @1269-1271 | 同名 | 1913-1921，1742、1758 | 3 |
| `DllTerrainIn15d` | `c_double[15]` @1275-1277 | 同名 | 1857-1864，1368、1405 | 11 |
| `DllInCtrlExt` | `c_double[140]` @1281-1283 | 同名 | 1926-1934 | 1 |
| `DllInFromUE` | `c_double[32]` @1287-1289 | 同名 | 1940-1947 | 1 |
| `DllGetStep0` | `restype c_double` @1300 | 同名 | 1965-1972（缺则回落 `0.001`），1614、1992 | 12 |
| `DllReInitModel` | `restype c_int` @1304 | 同名 | 1803-1808，1375 | 12 |
| `Dllstep` | `restype c_int` @1307 | 同名 | 1976-1981，1386、1996 | 12 |
| `DllOutCopterData` | `c_double[32]` @1311-1313，`restype None` @1314 | 同名 | **零参调用** `self.dll.DllOutCopterData(out_data)` @2025（包装 2021-2030） | 4 |
| `DlloutVehileInfo60d` | `c_double[60], c_int` @1317-1320，`restype None` @1321 | 同名 | 2003-2015，1394 | 11 |
| `DllDestroyModel` | `restype None` @1325 | 同名 | 1793-1798（**全文件内无任何调用点**） | 12 |

**缺失/不可达初始化分支（机器判定）**：没有任何"包装方法存在但完全未配置"的符号；唯一不可达配置是 **`DllInitPosAngState`** ——其两处 argtypes 块（1249-1252、1256-1259）**只**位于 `hasattr(self.dll,"DllInitPosAngStat")` 之下，而该名在本次 12 个与前置 18 个 PE 中**零出现**，故该分支对**每一个**已盘点二进制都不可达。

**生产端有、消费端无引用**（14 个）：`?DllCreatModel@@YAXXZ`、`DllGetGpsPos`、`DllInputPWMs`、`DlloutHILSensor30d`、`DlloutHILGPS30d`、`DlloutputSensors`、`DlloutputGPS`、`DlloutModel3DInfo`、`DllGetInitInputs`、`DllinCollision20d`、`DllInitParamAPI`、`DllFaultParamAPI`、`DllDynModiParams`、`DllInCopterData`、`DllGetExtToUE4`。**其中 `?DllCreatModel@@YAXXZ` 被 12/12 导出，却在消费端零引用**——创建入口从不由 Python 调用。

**消费端有引用、生产端零出现**：仅 **`DllInputDoubCtrls`**。

### 3.2 目标 DLL 身份（消费端自身规则）

- `1191-1195`：`PSP_PATH`（无则 `C:\PX4PSP`）→ `PSPDllPath = <psp>\CopterSim\external\model`；本机 `PSP_PATH=E:\rflysimtools`。
- `1197-1212`：绝对路径存在则用；否则 `sys.path[0]/<name>`，再否则 `PSPDllPath/<name>`，都不存在则打印后 `sys.exit(0)`。
- `1214-1219`：`CopterID>1` 时把 DLL **复制**为 `<name>_<id>.dll` 再加载 → 多机场景下"加载了哪个文件"进一步分叉。
- `1221`：`ctypes.CDLL(dll_full_name)` —— **cdecl 形态的加载**（仅记录消费端意图，不构成 ABI 权威）。
- `2096-2099`：`MultiCopterDll` 硬编码 `super().__init__('MulticopterNOpx4.dll', …)`；**全文件唯一的 `.dll` 字面量**。消费端从不点名 `Exp1_MinModelTemp.dll`。

### 3.3 补充：样本身份绑定（read-only 文本）

| 样本 | 脚本 SHA256 | 实例化的消费端类 | 批处理 `DLLModel` | 同胞 DLL |
| --- | --- | --- | --- | --- |
| 前置 c3 实际引用的样本 `…/12.DllModelImport/9.ModelLoadCopterSim30100Python/DllSimCtrlAPITest.py` | `3510c3a62611720d95ea65b08587713998b24aa607339a0dfa7413b69833b392` | **`DllSimCtrlAPI`（UDP 类，143）**，非 `ModelLoad` | `MulticopterNOpx4`（bat:27） | `MulticopterNOpx4.dll` 173568 B `0179c58f…`（**与部署副本逐字节相同**） |
| `…/11.inSILAPI/3.inSIL28d/2.sendInDoubCtrls/inSIL28dTest.py` | `37c955677faa041a968a1882c0f9a75328faedcca5aeab75d80e1c85b161a700` | **`DllSimCtrlAPI`（143）** | `Exp1_MinModelTemp`（bat:29） | `db33543c…` 224768 B，导出 `DllinSIL28d`+`DllinCollision20d`，**不导出** `DllInputDoubCtrls` |

两个样本都通过 `DllSimCtrlAPI.sendInDoubCtrls`（`348`）走 **UDP → CopterSim.exe → 模型 DLL**，**不经 ctypes**。因此 `DllInputDoubCtrls`（ctypes 直通名）与样本路径是**两条不同路径**：目录名恰为 `2.sendInDoubCtrls` 的样本，其二进制暴露的是 `DllinSIL28d`。

**对前置 c3 引用的更正（仅更正引用，不改其结论）**：前置 c3 以 `lunar-57/summary.md:27` 为据称"样例调用 `sendInDoubCtrls()`"。该行实读只说"supplied sample 只证明 legacy Python 调用意图"，**并未记录该调用**；该切片真正读取的样本是 `summary.md:18` / `abi-facts.json:27` 所列的 ModelLoad 30100 样本。结论（`DllInputDoubCtrls` 零出现）不受影响。

---

## 4. 对前置发现的复核（原结果一律保留）

| ID | 原结果 | 是否保留 | 净变化 |
| --- | --- | --- | --- |
| **c5** 双 `Exp1_MinModelTemp.dll` | 两个二进制同名 | **保留**（两哈希实读均与记录一致） | 歧义**变宽**：12 份拷贝 / 11 个二进制 / 7 个导出名集合，并新增第三份（e1 模板）。部署机制已实证（各自的同胞批处理复制），但当前部署的 `8134aab6…` 在树中无同胞来源 |
| **c6** e0 旧+新命名并存 | 只作总体陈述成立；逐文件不可核验 | **保留**（"无二进制同时具备两族"未被推翻） | 逐文件断言现**可核验且被推翻**：e0 模板**只有**现代名，部署副本**只有**旧名；26 并集中**零**个同时具备两族。受影响散文：`docs/coptersim-reconstruction.md:63`、`provenance-supplement.md:20` |
| **c7** e1 导出串来源 | 无路径/大小/哈希，不可复现 | **保留** | **可复现性闭合**：e1 模板 path/242176/`c2fbfd4d…`/`0x8664` 已记录，其 12 名 + 修饰 `?DllCreatModel@@YAXXZ` 与 supplement 列表**完全吻合**（supplement 写作未修饰 `DllCreatModel`）。仍只是"名字级"证据，不含任何类型/宽度/单位 |
| **c2** `DllInitPosAngStat` | 18 个 PE 中零出现；消费端缺陷；argtypes 永不安装 | **保留** | 零出现扩至 **26 并集**（本次 12 个中 0 出现）；缺陷绑定到 1248→1249、1255→1256，两块 argtypes **均**在异名守卫下不可达 |
| **c3** `DllInputDoubCtrls` | 无任何已盘点 DLL 导出该名 | **保留** | 零出现扩至 26 并集（`DllinSIL28d` 有 3 个）；"样例指向何处"半边已绑定：样本走 UDP，不由 Python 加载 DLL |
| **c1** `DllInputColls` 宽度 | `double[20]`→`float[20]`，宽度未决 | **保留** | 仅消费端细化：两个重复包装方法都构造 `c_float`（1847、1957），存活意图为 `float[20]`；**被调方宽度仍未决** |
| **c4** `DllOutCopterData` 形状 | 固定元数与零参调用不可能同真 | **保留** | 精确到行：argtypes `c_double[32]` @1311-1313、restype `None` @1314、零参调用 @2025 |
| **G1/G2/G8/G11** | 平台/无版本/修饰名/族不共存 | **保留** | 在新增 10 个二进制上**继续成立**，并集口径 26 |

---

## 5. 覆盖与未覆盖边界

**已覆盖**：11 个同名互异二进制 + 消费端硬编码目标的只读 PE header/import/export/version 表；e0/e1 模板与部署副本的 path/size/SHA/machine/完整 `Dll*` 导出名；前置 1234–1307 摘录的逐行一致性验证；构造函数块、命名解析、加载调用、CreateVehicle 次序、输入分发循环、包装方法、输出读取、控制编码器、硬编码默认目标的精确行号绑定；异名守卫与不可达 argtypes 块；两个相关样本的只读身份绑定。

**未覆盖（明确不声称）**：任何调用约定（除修饰名自身编码外未再推导）；任何参数类型、元素宽度、返回类型、单位、坐标系、次序、所有权、生命周期、行为；`CopterSim.exe`/`CopterSimNoUI.exe` 内部（含 28 维 UDP 载荷最终进入哪个导出）；不携带该文件名的其余 ApiExps DLL；其余 10 份同名拷贝的同胞批处理声明（建议 n8）；任何许可/允许使用；任何 manifest 实例、ABI 批准或互操作性。

---

## 6. 对 #9 blockers 的净变化

| Blocker | 净变化 | 状态 |
| --- | --- | --- |
| **B1** 无权威接口材料 | 无变化：本次只是元数据与文本，未发现也未产生任何头/规范/调用约定 | 仍阻塞 |
| **B2** 消费端冲突无法由消费端裁决 | **收窄**：c2、c3 获完整且机器可检的消费端解释，c4 精确到行；但 c1 的**被调方**宽度仍未知，且任何冲突都**推不出**原型 → 对 ABI 仍阻塞 | 收窄，仍阻塞 |
| **B3** 样本身份歧义 | **部分解除**：被引样本自身的目标二进制已命名并哈希（`MulticopterNOpx4.dll` 173568 B `0179c58f…`，与部署副本逐字节相同），部署机制已实证。仍未解：当前部署的 `8134aab6…` 无同胞来源；无批处理的裸脚本无绑定记录 | 部分解除，Exp1 链仍开 |
| **B4** 许可未记录 | 无变化（本次未调查，未发现任何声明） | 仍阻塞 |
| **B5** 无 manifest 实例 | 无变化：本次刻意不产出 manifest 候选 | 仍阻塞 |

**结论：没有任何 blocker 被清除，#9 的 DLL 半边维持 NO-GO。** 净收益是三条矛盾（c7 复现性闭合；c2/c3 获得完整消费端解释；c6 逐文件断言被推翻）从此建立在可复现、带哈希的证据之上，且请求外部材料时现在可以**按 SHA256 点名二进制**，而不是按文件名。

**下一动作**：`n3`（外部权威接口包，唯一能解除 B1/B2/B4 的路径，优先级 1）→ `n6`（把 `coptersim-reconstruction.md:63`、`docs/plan/model-reference-provenance-supplement.md:20` 改写为逐文件矩阵，现已可执行）→ **`n8`（新，低代价离线）**：为其余 10 份同名拷贝逐一记录其同胞批处理的 `DLLModel` 声明与部署目标，把"样本→二进制"绑定逐实验钉死。`n7`（相邻 #75 静态门禁）本次未重跑，状态不变。

---

## 7. 稳定 SHA 与交付范围

| 项 | 值 |
| --- | --- |
| 派发时 HEAD | `0239f0e459bd8f5d7cdc6c25c0c6aa6687ead54f` |
| 交付时 HEAD | `33c2b06e8794ad865a25b307852d08d4c0845a26` |
| 架构祖先 | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`（祖先检查退出码 0，两次） |
| 证据输入漂移 | 0（消费端与前置摘录哈希均实读复核；HEAD 推进后三步全量重跑） |
| `evidence.json` SHA256 | `01a5c15b429cf46df8f252e62104c5d31389329cd7e5ed2ba71d8ddbd26862dc` |
| 行尾 | 全部产物 LF（`.gitattributes` = `* -text` 冻结） |
| 本次写入 | 仅本目录内 10 个文件（见 `manifest.json`）；**交付后停止写入** |
| 提交归属 | 主会话（本目录被 `.gitignore:53` `/validation/*/` 忽略；前置审计即由主会话于对端提交 `09105fa` 录入） |

**本次未写入**：共享账本、adapter、`Simulator/**`、任何 Issue、任何厂商路径、任何其他 `validation/` 目录、以及前置审计目录的任何字节。

## 8. 非声称

1. 本切片不批准任何 DLL 的任何 ABI，旧新皆不批准；不改变 #9/#27/#28/#73/#74/#76/#77/#78 的状态。
2. 未加载、映射、执行、反编译、反汇编或做类型恢复；`.bat` 仅作文本读取且**未执行**，其复制指令的运行期效果**未被观察**。
3. 二进制元数据只确立导出名存在与拼写、名字修饰、模块机器类型与静态导入；不确立参数类型、元素宽度、返回类型、单位、坐标系、所有权、生命周期或行为。
4. 消费端 ctypes 声明与包装体一律记为**意图**，绝不作为 ABI 权威；未从消费端反推任何 ABI。
5. **不声称** `DllInputDoubCtrls` 与 `DllinSIL28d` 语义等价，也**不声称** `CopterSim.exe` 的 28 维 UDP 载荷路由到哪个导出（其内部未盘点）。
6. 未复制、修改或发布任何厂商源码、头文件、二进制或安装；不推断任何再分发权利；仅记录元数据与单行文本引用。
7. 不声称任何数值、物理、时序、互操作或兼容性验收；#23/G6 预算未被触及。
8. "在已盘点总体中零出现"只是关于**已盘点二进制**的事实；16 个部署 DLL + 10 个新盘点的同名二进制**不等于**全部厂商面。
9. 本切片不审阅或认可任何对端提交的内容（包括录入前置审计的 `09105fa`）。
