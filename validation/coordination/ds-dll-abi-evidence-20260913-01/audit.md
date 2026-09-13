# #9 DLL/模型插件 ABI 证据审计与权威缺口矩阵

- `checked_at`: `2026-09-13T22:17:12+09:00`
- 工作类别：`historical-material/read-only ABI evidence audit`。**不是**新架构实现、不是 ABI 批准、不是兼容性验收。
- 交付目录（独占写入）：`validation/coordination/ds-dll-abi-evidence-20260913-01/`
- 机器可读矩阵：[audit.json](audit.json)，SHA256 `42e574e1f079f3f3017215db2ca60c46c8c8678ac773be9319f4cf5712692420`
- 本页与 `audit.json` 是本次唯一交付物；本目录另有 `.gitattributes` 冻结行尾，使记录哈希不因 CRLF 检出漂移。

---

## 1. 开工核验（实际执行）

| 项 | 值 |
| --- | --- |
| 实际 cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| 分支 | `main` |
| 派发时 HEAD | `abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18` |
| 交付时 HEAD | `7e1e137879a779f2b051b384c044e6e936878d53` |
| 审计期间 HEAD 变动 | 两次：`abf1ac3` → `0779f43`（对端提交 `Record three DeepSeek evidence audits`）→ `7e1e137`（对端提交 `Record G6 per-quantity evidence audit`，即同级审计 `ds-g6-budget-evidence-20260913-01/`）。两次均未触及本次任何证据输入。 |
| 架构祖先检查 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → 退出码 **0**（派发时与交付时各一次） |
| 证据输入漂移 | 15 份已哈希输入在**每一次** HEAD 变动后逐一复核，**漂移 0** |

**本审计绑定的是 15 份已哈希证据输入，不是移动的分支尖端。**

已读：`AGENTS.md`、`CONTEXT.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/module-delivery-policy-20260912.md`、`docs/coordination/short-cycle-goal.md`。

遵守的禁止项：未猜测 ABI；未逆向、未反汇编、未做类型恢复；**未加载或运行任何 DLL/模型**；未复制或发布厂商材料；未执行 native/构建/ROS/飞控/模型/UE/MATLAB；未修改任何 Issue；未写共享账本或 adapter。

本次实际执行的只读命令（全部离线，无副作用）：

```text
gh issue view {1,9,27,28,57,58,73,74,76,77,78} --repo unununnnn/wksim --json ...
gh issue list --repo unununnnn/wksim --state all --limit 300 --json number,title,state
# 只读 PE 元数据审计（读取仓库内既有清单，不触碰二进制）
Get-FileHash -Algorithm SHA256 work/coptersim-compat-20260905/evidence/pe-inventory.json
# 离线纯测试（不加载库、不建原生、不改仓库）
python -B -m unittest validation.test_validate_legacy_abi_manifest   # 23 ran / 22 ok / 1 skipped / exit 0
python -B -m unittest validation.test_audit_core_no_vendor_dll        # 70 ran / 68 ok / 2 FAIL / 1 skipped / exit 1
```

`python -B` 与 `PYTHONDONTWRITEBYTECODE=1` 已设置；测试未在仓库内产生任何文件。

---

## 2. 证据类别定义

| 代码 | 含义 |
| --- | --- |
| **P** | 已由公开或仓库材料证明：可读文本、已记录哈希，或**未执行**的二进制导出/元数据表 |
| **I** | 仅推断：消费端 ctypes 形状、符号名、命名约定，或单一二手记录 |
| **C** | 相互矛盾或材料间不一致 |
| **M** | 完全缺失 |

**类别的证明边界**：二进制元数据只能证明导出名存在与拼写、名字修饰、模块机器类型与静态导入；**不能**证明参数类型、元素宽度、返回类型、单位、坐标系、所有权、生命周期或行为。

---

## 3. 证据源清单（含 SHA256）

| 证据 | 路径 | SHA256 | 跟踪 |
| --- | --- | --- | --- |
| SDK ctypes 消费端 | `E:/rflysimtools/RflySimAPIs/RflySimSDK/ctrl/DllSimCtrlAPI.py` | `0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420` | 否（厂商安装） |
| 18 个 PE 只读导入/导出/版本表 | `work/coptersim-compat-20260905/evidence/pe-inventory.json` | `7eb4e8d11244e564ee3fe61482ecda141c9cc46c32e26b5ab4e7a8c811f6f6bc` | **否（本地未跟踪）** |
| #57 ABI 证据合同 | `docs/plan/9-abi-environment-evidence.md` | `606cb49eb7f226946793df8a6d0e536c867e00d5e9a431c47595a39cb1e91331` | 是 |
| #58 已批准/阻塞记录 | `docs/plan/9-abi-environment-accepted.md` | `0053b43d5ed156d6b14d5d5a5f80acc0ea280c3609d11a96ed9a5913c83bac4c` | 是 |
| #57 事实 JSON | `validation/lunar-57-.../abi-facts.json` | `438ca221e83678e8c9ee0092cc8e4a12fdec98e95cb2100d473a3053f788ae56` | 是 |
| 消费端行摘录 | `validation/model-reference-provenance-20260907/sdk-wrapper-evidence.json` | `bc0b07ab00455ff6a8aefea1e363077f577590d2d9c8c4a6674746a14b113d60` | 是 |
| 12 份 e0 模板资源哈希 | `validation/model-reference-provenance-20260907/resource-hashes.json` | `1f60ba27efbc892470165c08e12033d6adb476aa96b201bb8a3451af5110dda6` | 是 |
| G6 来源核对 | `docs/plan/model-reference-provenance.md` | `2c903707c1b655009ee8a9b62ec305ecb84562e54d852d09252d0a4c35bdef0d` | 是 |
| G6 来源补充（e1 导出串） | `docs/plan/model-reference-provenance-supplement.md` | `34fa8892e2e86be697a736b0932b8ad7accbcab0ceeacb13d45df8b1a2944cda` | 是 |
| 下一条参考接缝 | `docs/plan/2026-09-07-reference-next-seam.md` | `1d1712ba7781a4bda2358d1fed20cf75c26ab767b229f94d711899a9af19be10` | 是 |
| manifest 提案模板 | `docs/plan/27-legacy-abi-manifest-proposal.md` | `464de8c5a2a3f55cf5d574f8f49e7f6b0091feb666f54771c7748c9ffaa08460` | 是 |
| manifest schema | `docs/plan/27-legacy-abi-manifest.schema.json` | `8f06c1c25c39ff8208e9843dfb1f9493425809e037b2ed778c42490431680457` | 是 |
| manifest 校验器 / 纯测试 | `tools/validate_legacy_abi_manifest.py` / `validation/test_validate_legacy_abi_manifest.py` | `f241c838...` / `962115e8...` | 是 |
| 接口决策包 | `docs/coordination/ds-interface-decision-packet-20260912.md` | `a7cfe224f2528a5651c6037eae7cf1547ae57e1dfe210c7792308ad247d5e382` | 是 |
| 当前检查点 | `docs/coordination/short-cycle-goal.md` | `d6339f23b61e3b1fee4e5d729b283bf1378da2622d9538a8ce29affaa606c71c` | 是 |
| Exp2 合同 | `docs/plan/full-contracts/model-16-exp2.json` | `8a191c857c814acd9ba0ff56857ca70c073519b97359c74e6996f7e08f05e90c` | 是 |

Issue 只读：`#9`（OPEN，含 4 条评论）、`#1`、`#57`/`#58`（CLOSED）、`#27`/`#28`/`#73`/`#74`/`#76`/`#77`/`#78`/`#26`（OPEN）、`#75`（CLOSED）。

---

## 4. 权威缺口矩阵

### 4.1 总览

矩阵为 **34 个符号 × 8 个维度 = 272 格**。逐格结论见 [audit.json](audit.json)，本页给出汇总与关键行。

| 类别 | 格数 | 占比 |
| --- | --- | --- |
| **P** 证明 | 71 | 26.1% |
| **I** 仅推断 | 26 | 9.6% |
| **C** 矛盾 | 4 | 1.5% |
| **M** 缺失 | 171 | 62.9% |

已证明的 71 格高度集中在两个维度：**`function`（导出名存在与拼写）**与 **`platform`**。**调用约定、数据布局、单位、生命周期、版本、许可**六个维度几乎全空。

### 4.2 横切结论（对全部 34 行生效）

| ID | 类 | 结论 | 依据 |
| --- | --- | --- | --- |
| G1 | **P** | 16 个模型 DLL 全部为 AMD64 PE（`machine=0x8664`），无 CLR 目录，静态导入**仅 `KERNEL32.dll`**。 | `pe-inventory`；`docs/coptersim-reconstruction.md:61-65` |
| G2 | **P** | 16 个模型 DLL 的 `version_strings` **全为空**，无 FileVersion/ProductVersion/ProductName。 | `pe-inventory` |
| G3 | **P** | 两个模板目录与已检索的 `E:/rflysimtools` 树中**不存在**实现 Dll* 导出包装的 `.h/.hpp/.c/.cpp/.def/.lib`；只有 `.p` 构建助手与 ctypes 消费端。 | `provenance-supplement.md:12`；`provenance.md:31,33`；`ds-interface-decision-packet:53` |
| G4 | **M** | **无任何材料**把任一 DLL 绑定到其生成 ZIP/SLX/init 修订；e0 链自身不一致（SLX 11.8 vs ZIP 11.0）。 | `provenance.md:15,17`；`reference-next-seam.md:21` |
| G5 | **M** | **无任何**厂商模型 DLL 的许可或允许使用声明；再分发明确未确认。 | `9-abi-environment-accepted.md:50`；`Simulator/wksim_core/README.md:5` |
| G6 | **M** | 除 `DllCreatModel` 外全部 Dll* 导出**未修饰**，没有任何编码或记录的调用约定；cdecl 与 stdcall 二者材料均未裁定。 | `pe-inventory` 导出名 |
| G7 | **P** | 厂商消费端是**条件超集适配器**：每个符号都在 `hasattr()` 守卫下配置，因此每样本的有效 ABI 是**逐文件子集**而非共享合同。 | `sdk-wrapper-evidence.json:1236,1242,1248,1255,1262,1268,1274,1280,1286,1293,1299,1303,1306` |
| G8 | **P** | 16 个 DLL **全部且仅**导出一个修饰 C++ 符号 `?DllCreatModel@@YAXXZ`，且**没有**未修饰的 `DllCreatModel`。按 MSVC 修饰规则该名编码 `void __cdecl DllCreatModel(void)`；因此按名解析必须使用该修饰串。 | `pe-inventory` 全部 16 文件导出表 |
| G9 | **P** | `DllGetStep0` 仅在 `MultSILSwarm.dll` 中缺失（16 中 15）；消费端的 `0.001` 回退路径因此**至少被一个已盘点样本触发**。 | `pe-inventory` |
| G10 | **P** | 同一概念在不同样本用**不同导出名**：碰撞输入 `DllInputColls`(2) vs `DllinCollision20d`(1)；SIL 输入 `DllInputSILs`(4) vs `DllinSIL28d`(1)；地形输入 `DllTerrainIn15d`(8) vs `DllInputTerrain`(7)。**没有任何单一 DLL 同时导出任一配对的两名。** | `pe-inventory` |
| G11 | **P** | **没有任何**已盘点模型 DLL 同时导出旧输出名族（`DlloutputSensors`/`DlloutputGPS`/`DlloutModel3DInfo`）与现代族（`DlloutHILSensor30d`/`DlloutHILGPS30d`）。族属**逐文件**属性，不是产品属性。 | `pe-inventory` 族分类 |

**16 个模型 DLL 的族分类（本次新算）：**

| 族 | DLL |
| --- | --- |
| 旧导出名族（`DlloutputSensors`/`DlloutputGPS`/`DlloutModel3DInfo`） | `CarNoCtrl`、`CopterSILVelCtrl`、`DllSilNoPX4TempDemo`、`Exp1_MinModelTemp`、`FixWingModel`、`MultSILSwarm`、`SmallFixedWingUAVnoctrlHIL`、`Trailer` |
| 现代 `*30d`/`*60d` 族 | `CarAckerman`、`CarR1Diff`、`MulticopterNoCtrl`、`MulticopterNoCtrlWithCollision`、`MulticopterNOpx4` |
| 现代族 + 扩展导出 | `AircraftMathworks`、`Exp2_MaxModelTemp`、`VtolHighModel` |

16 个 DLL 合并后共 **31 个不同 `Dll*` 导出名**（`audit.json` 逐名给出出现次数与族）。`Exp2_MaxModelTemp.dll` 是唯一带全套扩展名（`DllInCtrlExt`/`DllInFromUE`/`DllFaultParamAPI`/`DllInitParamAPI`/`DllDynModiParams`/`DllGetExtToPX4`/`DllGetExtToUE4`/`DllinCollision20d`/`DllinSIL28d`）的样本。

### 4.3 逐符号关键行（完整 34 行见 audit.json）

`P/I/C/M` 顺序为：函数 → 调用约定 → 数据布局 → 单位/坐标/次序 → 生命周期/所有权 → 版本 → 平台 → 来源许可。

| 符号 | 出现 | 族 | P/I/C/M | 关键点 |
| --- | --- | --- | --- | --- |
| `DllCreatModel`（修饰名） | 16 | 共享 | **P P P P** M M **P** M | 唯一**调用约定已证明**的导出；修饰名即导出表条目 |
| `DllDestroyModel` | 16 | 共享 | **P** M I I M M **P** M | 幂等性、线程/UDP 释放全缺 |
| `DllInitPosAngState` | 16 | 共享 | **P** M I I M M **P** M | 消费端两个 `double[3]`；**其 argtypes 因 C2 永不安装** |
| `DllInputPWMs` | 16 | 共享 | **P** M I M I M **P** M | 生成根输入 `inPWMs[16]` 仅佐证长度，不证明导出参数 |
| `DllReInitModel` | 16 | 共享 | **P** M I **P** M M **P** M | reset 是否恢复全部随机状态**明确未解** |
| `Dllstep` | 16 | 共享 | **P** M I **P** M M **P** M | 返回/错误码、短输出、步长语义全缺 |
| `DllGetStep0` | 15 | 共享 | **P** M I I M M **P** M | 缺于 `MultSILSwarm`；`0.001` 回退被触发 |
| `DllInitGpsPos` | 14 | 共享 | **P** M I I M M **P** M | 分量语义（经纬高 vs NED）未定 |
| `DllInCopterData` | 10 | 现代状态输入 | **P** M **M M M** M **P** M | 无消费端形状、无生成根端口 → 全空 |
| `DllGetGpsPos` | 8 | — | **P** M **M M M** M **P** M | 输出长度/元素类型未知 |
| `DlloutModel3DInfo` | 8 | 旧输出 | **P** M **M M M** M **P** M | `ClassID=-1` 不是资产绑定 |
| `DlloutVehileInfo60d` | 8 | 现代输出 | **P** M I M M M **P** M | 拼写（含 `Vehile` 误拼）**已冻结**；60 宽度由名字与根端口双源佐证 |
| `DllTerrainIn15d` | 8 | — | **P** M I M I M **P** M | 消费端 `double[15]` + 根端口 `[15]` 双源佐证 |
| `DllInputTerrain` | 7 | 旧输入 | **P** M **M M M** M **P** M | 与 `DllTerrainIn15d` 互斥（G10） |
| `DlloutHILGPS30d` | 7 | 现代输出 | **P** M I M M M **P** M | 30 由名字与根端口佐证；逐元素单位缺 |
| `DlloutHILSensor30d` | 7 | 现代输出 | **P** M I M M M **P** M | 同上 |
| `DllGetInitInputs` | 6 | — | **P** M **M M M** M **P** M | 全空 |
| `DlloutputGPS` | 6 | 旧输出 | **P** M **M M M** M **P** M | 全空 |
| `DlloutputSensors` | 6 | 旧输出 | **P** M **M M M** M **P** M | 全空 |
| `DllInputSILs` | 4 | 旧输入 | **P** M I M I M **P** M | 消费端 `int[8]+float[20]`；SLX 注释佐证 8 |
| `DllGetExtToUE4` | 3 | 扩展 | **P** M **M M M** M **P** M | UE 边界坐标/单位完全未记录 |
| `DllOutCopterData` | 3 | 旧输出 | **P** M **C** M M M **P** M | 见 C4 |
| `DllInputColls` | 2 | 旧输入 | **P** M **C** M I M **P** M | 见 C1 |
| `DllDynModiParams` | 1 | 扩展 | **P** M **M M M** M **P** M | 参数是否可 epoch 内变更未证 |
| `DllFaultParamAPI` | 1 | 扩展 | **P** M **M M M** M **P** M | `FaultInParams` 未建立到生成参数的映射 |
| `DllGetExtToPX4` | 1 | 扩展 | **P** M **M M M** M **P** M | 全空 |
| `DllinCollision20d` | 1 | 扩展 | **P** M I M M M **P** M | 佐证长度 20，不裁定宽度 |
| `DllInCtrlExt` | 1 | 扩展 | **P** M I M I M **P** M | 140 维语义全缺 |
| `DllInFromUE` | 1 | 扩展 | **P** M I M I M **P** M | UE→模型新鲜度语义缺 |
| `DllInitParamAPI` | 1 | 扩展 | **P** M **M M M** M **P** M | 全空 |
| `DllinSIL28d` | 1 | 扩展 | **P** M I M **M** M **P** M | 28 由名字与消费端佐证 |
| `DlloutputStateQuat` | 1 | 旧输出 | **P** M **M M M** M **P** M | 四元数次序未知 |
| `DllInitPosAngStat` | **0** | 消费端引用但不存在 | **C** M M M M M **P** M | 见 C2；18 个 PE 中**零出现** |
| `DllInputDoubCtrls` | **0** | 消费端引用但不存在 | **C** M M M M M **P** M | 见 C3；18 个 PE 中**零出现** |

### 4.4 已证实的矛盾（7 项，完整文本见 audit.json）

| ID | 类 | 状态 | 内容 |
| --- | --- | --- | --- |
| **C1** `dllinputcolls-width` | C | 已记录为阻塞 | 同一消费端把 `DllInputColls` 先声明 `c_double[20]`（1237–1239）后覆盖为 `c_float[20]`（1294–1296）。**宽度未决。**本次新增佐证：`DllinCollision20d` 佐证长度 20，但**不裁定** float/double。 |
| **C2** `dllinitposang-name` | C | 已记录为阻塞 | 消费端在 1248/1255 检查 `DllInitPosAngStat` 却访问 `DllInitPosAngState`。**本次新证**：`DllInitPosAngStat` 在 18 个 PE 中零出现 → 这是真实的消费端缺陷，且意味着该路径上 `DllInitPosAngState` 的 argtypes **永不安装**。 |
| **C3** `inputdoubctrls-absent` | C | **本次新增** | 消费端配置 `DllInputDoubCtrls` 且样例调用 `sendInDoubCtrls()`，但**无任何已盘点模型 DLL** 导出该名（只有 `DllinSIL28d`，仅 Exp2）。要么样例指向已盘点目录之外的 DLL，要么该旧控制路径在此总体中是死路。 |
| **C4** `outcopterdata-shape` | C | 部分已记录 | 构造期声明 `argtypes=[double[32]]`，但后续包装方法重新分配数组并以**零参数**调用；固定元数与零参调用不可能同时对。 |
| **C5** `exp1-two-binaries` | C | **本次新增** | **两个不同二进制共用文件名 `Exp1_MinModelTemp.dll`**：e0 模板副本（235520 B，`30747a8d…`，正是 G6 来源链绑定的哈希）与部署副本 `CopterSim/external/model/`（230912 B，`8134aab6…`）。无材料解释差异，也无材料说明 SDK 样例或 SITL 批处理实际加载哪一个。**后果**：任何"e0 DLL ABI"陈述目前在两个不同导出族的二进制之间歧义（部署副本是纯旧输出名族；模板副本的导出表从未被盘点）。 |
| **C6** `e0-old-and-new-naming` | C | **本次新增** | `docs/coptersim-reconstruction.md:63` 与 `provenance-supplement.md:20` 称模型 DLL（补充文档更具体地称 e0 DLL）**同时**有旧输出名与新输出名。就 16 个已盘点 DLL 而言，这只在**总体层面**成立：**没有任何单一 DLL 同时具备两族**。关于 e0 DLL 的逐文件断言因 C5 无法核验。 |
| **C7** `e1-export-string-provenance` | C | **本次新增** | e1 导出名证据（`provenance-supplement.md:12`）是**没有记录文件路径、大小或 SHA256** 的二进制字符串观察，而它却是"DllInitPosAngState 才是正确名"这一断言的**唯一来源**。e1 的 SLX/ZIP/init 哈希有记录，**e1 DLL 哈希没有**。最强的"导出是什么"证据目前无法仅凭仓库材料复现。 |

### 4.5 完全缺失项（13 项）

| ID | 缺失内容 | 影响 |
| --- | --- | --- |
| M1 | 任一采样的权威可读 C/C++ 头、`.def` 或 `.lib` | 阻塞 #58 五项前置的**每一个**逐导出字段 |
| M2 | 每个导出的返回类型与错误码契约 | `Dllstep`/`DllReInitModel`/`DllDestroyModel` 的失败语义无法陈述 |
| M3 | 每个输出导出的缓冲分配与所有权 | 无法导出任何安全的输出读取设计 |
| M4 | 加载→初始化→输入→step→读取→重置 epoch→终止/卸载状态机 | schema 强制要求恰好 6 个状态与可达转移图，材料无一行可填 |
| M5 | 崩溃/step 错误/短输出/重复 reset/线程与 UDP 残留的隔离行为 | #27 AC3（宿主崩溃或不兼容 DLL 被隔离）无证据基础 |
| M6 | 线程模型、可重入性与进程/UDP socket 所有权 | 隔离宿主设计无法定界 |
| M7 | 120 个输出标量（30+30+60）的逐元素单位、坐标系与次序 | #23/G6 数值预算在该路径上无法定义 |
| M8 | 每个导出名到生成模型方法或根端口的交叉表 | `reference-next-seam.md` 要求的 crosswalk **无行可填** |
| M9 | 样例实际加载哪个 DLL 二进制、SITL 批处理部署哪个 | 见 C3/C5；无样本可被命名为已批准的 ABI 对象 |
| M10 | 每个厂商模型 DLL 的许可与允许本机使用 | #58 前言中的硬阻塞，与全部技术工作正交 |
| M11 | reset 是否恢复全部随机状态、逐组种子契约 | schema 的 `reset_restores_random_state` 无法据证据填写 |
| M12 | `VisionSensorReq` 的权威定义及其 epoch/权威 step/新鲜度语义 | #28 扩展输出只有 16H28f 注释级字段线索 |
| M13 | 任一 DLL 到其源码修订的构建绑定 | 无法为任何 DLL 定版，因而无法冻结 ABI 到修订 |

---

## 5. 明确阻断项

| ID | 阻断 | 后果 | 归属 |
| --- | --- | --- | --- |
| **B1** | 仓库、两个模板目录与已检索厂商树中**不存在**任何旧或新 DLL ABI 的权威接口材料 | #73/#74/#76/#77/#78/#27/#28 保持阻塞；#9 的 DLL 半边维持 **NO-GO** | 外部材料 / 用户决定 |
| **B2** | 消费端冲突集（C1–C4）无法仅由消费端材料裁决；用 ctypes 反推即为猜测，明令禁止 | 任何 manifest 都必须靠**虚构原型**才能填满 | 用户/Astra 决策票 |
| **B3** | 样本身份歧义（C5）且样例目标 DLL 未记录（C3/M9） | 不存在可被 #27/#28 消费的**可命名已批准 ABI 对象** | 外部材料 |
| **B4** | 厂商模型 DLL 的许可/允许使用未记录（M10） | 即使技术 manifest 完美也无法被接受 | 用户 |
| **B5** | 仓库中**不存在任何 manifest 实例**，只有 schema 与校验器 | #27 门禁的输入为零；磁盘上现有任何东西都无法满足它 | 流程 |

**结论**：在 B1–B5 解除前，不得派发 #73/#74/#76/#77/#78 的 ABI 实现或运行切片，也不得从任何 ctypes 形状推断宿主或 adapter（与 #9 评论一致）。

---

## 6. 最小后续可执行取证 / 重核计划

只列**最小**且**可执行**的步骤；不得猜测 ABI、不得逆向、不得运行 DLL/模型。

| # | 优先 | 动作 | 入口（已核对真实参数面） | 验收 | 能证明 | **不能**证明 |
| --- | --- | --- | --- | --- | --- | --- |
| **n1** | 1 | 只读盘点 e0 模板 DLL 与 e1 模板 DLL，记录 path/size/SHA256/导出表/machine/imports，闭合 **C5/C6/C7** | `work/coptersim-compat-20260905/inspect_pe.py` 的 `__main__` **硬编码**目标列表（`E:/rflysimtools/CopterSim` + `external/model`）且**拒绝覆盖**既有输出；可复用的只读 API 是 `inspect_pe.inspect(path)`（pefile `fast_load`，**不执行**）。需新建同级工具或新输出路径。 | 每个候选样本都有 path/size/sha256/machine/imports 与完整 `Dll*` 导出表 | 每个候选**实际拥有**哪些导出名与族 | 调用约定（修饰的 `DllCreatModel` 除外）、参数类型、单位、生命周期、许可、版本绑定 |
| **n2** | 1 | 补齐消费端行摘录：只读重读 `DllSimCtrlAPI.py`，记录 `ModelLoad.__init__` 构造、`CreateVehicle`、输出读取、`sendInDoubCtrls`、`InitTrueDataLoop`、关闭路径的**精确行号**与哈希 | 现有摘录仅覆盖 **1234–1307 行** | schema 需要的每个符号都有引用行区间，或**显式标记不存在** | 消费端真实条件调用图与 C2/C3/C4 背后的缺符号事实 | 被调方 ABI——消费端材料**永远不是** ABI 权威 |
| **n3** | 2 | 向材料归属方索取**绑定到某个已命名样本二进制**的权威接口包：头/规范、调用约定、精确 float 宽度、返回/错误契约、缓冲所有权、生命周期状态机、线程/隔离契约、构建清单、许可与允许使用 | 无命令；这是外部材料请求，已作为决策项 A1 记录于 `ds-interface-decision-packet-20260912.md:55` | `9-abi-environment-accepted.md:28-34` 的 #58 五项前置**全部**可由收到的材料满足 | 其本身不证明任何事；它**解除阻塞** | 互操作性——manifest 仍需一次真实隔离生命周期运行 |
| **n4** | 2 | 若 n3 无法满足，则**正式决定放弃**旧/新 DLL 运行路径，仅保留自主 `wk_model_*` seam，并在 #9 记录该决定 | 用户决定；替代方案已作为决策项 A1 框定 | #27/#28/#73/#74/#76/#77/#78 要么重新界定范围，要么显式作为放弃关闭 | 无技术结论 | 不证明 DLL 导入能力不可实现；它记录的是**范围决定** |
| **n5** | 2 | 保持 ABI 门禁机器可检：未来任何 manifest 候选必须通过既有 fail-closed 校验器，且 exit 0 **继续**只表示"结构完整、仍未批准" | `python -B tools/validate_legacy_abi_manifest.py MANIFEST [--output REPORT]`；离线测试 `python -B -m unittest validation.test_validate_legacy_abi_manifest`（**本次实跑**：23 ran / 22 ok / 1 skipped / exit 0） | manifest 恰好声明两个已钉冲突、六个生命周期状态、非占位隔离陈述，以及带哈希的可读包装/样本链 | 结构完整性，且占位词与自声明批准无法溜过 | ABI 批准、互操作、数值正确性或 #6/G6 预算满足 |
| **n6** | 3 | 修正本审计发现的**表述范围错误**：把总体层面的"旧新命名并存"句子（`coptersim-reconstruction.md:63`、`provenance-supplement.md:20`）改写为逐文件矩阵形式，并补记 e1 导出串的来源（C7） | 由文件归属写者编辑；**不在本次写入范围** | 不再有句子断言与盘点相矛盾的逐 DLL 导出族 | 无技术结论 | 任何 ABI |
| **n7** | 3 | 把相邻的 #75 静态门禁失败转交其归属方（见第 7 节） | `python -B -m unittest validation.test_audit_core_no_vendor_dll` | 真实仓库测试在当前 HEAD 通过 | 连续的无厂商 DLL 门禁重新反映现实 | #9 ABI 状态，或既有 #75 运行证据失效 |

**建议先执行 n1 + n2**：两者都完全离线、无厂商执行、成本低，且直接闭合 3 项本次新增矛盾（C5/C6/C7）与 1 项新增矛盾（C3）。它们**不会**解除 B1/B2/B4，因此**不会**解锁 #27/#28。

---

## 7. 相邻发现（不在 #9 ABI 矩阵范围内）

**A1 — #75 支撑性静态门禁在当前 HEAD 为 RED。**

`python -B -m unittest validation.test_audit_core_no_vendor_dll` → **70 ran / 68 ok / 2 FAIL / 1 skipped / exit 1**。失败项为 `RealRepositoryTests.test_real_core_passes` 与 `RealRepositoryTests.test_cli_exit_codes`；审计报告 `Simulator/wksim_runtime/perf_capture.py:51` 与 `Simulator/wksim_runtime/netns_handoff.py:183` 存在钉定单点之外的意外动态加载点。

- 四个相关文件在工作树中**均已提交且 clean**：工具钉定于 `ec40ec2`（2026-09-12 `Reject ctypes module escapes in the core static audit`），`perf_capture.py` 由 `ee9312a`（2026-09-13 `Add native-verified perf capture adapter`）引入。
- **与本次的关系**：该门禁编码的正是"自主核心保持封闭的厂商 DLL/加载器面"这一不变量，也正是"#9 阻塞"之所以安全的前提。它**不是** #9 ABI 矩阵的一部分，也不是关于任何厂商 ABI 的证据。
- **不声称**：这不使已关闭的 #75 运行证据（`validation/lunar-27-core-without-dll/run-ec40ec2-01`）失效，也不对厂商 ABI 说任何话。
- 建议下一动作：n7。

**A2 — 审计期间 HEAD 前进两次。** HEAD 由 `abf1ac3` → `0779f43`（对端提交，仅触及 `validation/coordination/three-deepseek-expansion-20260913-01/`）→ `7e1e137`（对端提交 `Record G6 per-quantity evidence audit`，即同级审计目录 `ds-g6-budget-evidence-20260913-01/`）。15 份已哈希证据输入在两次变动后**全部复核未漂移**；祖先检查在交付时仍为退出码 0。本审计不审阅或认可这两次对端提交的内容。

**A4 — 本交付目录被 `.gitignore:53`（`/validation/*/`）忽略。** 文件已落盘并哈希，但 `git status` 不显示它们。惯例（同级 `ds-g6-budget-evidence-20260913-01/`）是**由主会话提交**该交付（对端审计即由主会话提交为 `7e1e137`）。按 [模块交付策略](../../../docs/coordination/module-delivery-policy-20260912.md) 第 3、8 条，本切片交付稳定 SHA 后停止写入，由主会话精确 `git add` 并提交已验证版本。

**A3 — 存在两份互不重叠的厂商参考复核。** `provenance-supplement.md:12` 得出 `DllInitPosAngState` 才是正确名并列出 e1 导出集；`9-abi-environment-evidence.md` 记录 SDK 消费端的 `DllInitPosAngStat` 冲突但**不含** e1 列表。二者一致但**不可联合复现**（C7）。**不声称**二者矛盾。

---

## 8. 稳定 SHA 与交付范围

| 项 | 值 |
| --- | --- |
| 派发时 HEAD | `abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18` |
| 交付时 HEAD | `7e1e137879a779f2b051b384c044e6e936878d53` |
| 架构祖先 | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`（祖先检查退出码 0，派发时与交付时各一次） |
| `audit.json` SHA256 | `42e574e1f079f3f3017215db2ca60c46c8c8678ac773be9319f4cf5712692420` |
| `audit.md` SHA256 | 见交付回复（无法自嵌） |
| 行尾 | 两者均为 LF（`.gitattributes` 冻结） |
| 本次写入 | 仅 `validation/coordination/ds-dll-abi-evidence-20260913-01/{audit.md,audit.json,.gitattributes}`；**交付后停止写入** |
| 提交归属 | 主会话（本目录被 `.gitignore:53` 忽略，需 `git add -f`；同级审计由主会话提交为 `7e1e137`） |

**本次未写入**：共享账本、adapter、`Simulator/**`、任何 Issue、任何厂商路径、任何其他 `validation/` 目录。并发对端目录 `validation/coordination/ds-g6-budget-evidence-20260913-01/` 与 `validation/coordination/three-deepseek-expansion-20260913-01/` 在审计期间被他人写入，本审计**未触碰**。

## 9. 非声称

1. 本审计不批准任何 DLL 的任何 ABI，旧新皆不批准；不改变 #9/#27/#28/#73/#74/#76/#77/#78 的状态。
2. 未加载、执行、反编译、反汇编或做类型恢复；未从代码恢复任何调用约定或类型。
3. 二进制元数据只确立导出名存在、拼写、名字修饰、模块机器类型与静态导入；不确立参数类型、元素宽度、返回类型、单位、坐标系、所有权、生命周期或行为。
4. 消费端 ctypes 声明一律记为**意图**，绝不作为 ABI 权威（与 `9-abi-environment-accepted.md:36` 一致）。
5. 未复制、修改或发布任何厂商源码、头文件、二进制或安装；不推断任何再分发权利。
6. 不声称任何数值、物理、时序、互操作或兼容性验收；#23/G6 预算未被触及。
7. 2026-09-07 已批准的环境/RGB 合同仅被引用，未被重新决定，也不延伸到 DLL ABI。
8. 校验器 exit 0 继续只表示"结构完整、未批准"，绝不可读作 ABI 验收。
9. `pe-inventory.json` 是**本地未跟踪**产物（仓库中不存在该文件的跟踪副本）；本审计记录其哈希以保证可复现，但不确立这些厂商文件在更晚时刻仍与哈希一致。
