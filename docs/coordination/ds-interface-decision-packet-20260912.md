# DS-C 接口决策包：#9/#29 阻塞项的可审阅决策清单

2026-09-12。滚动队列 DS-C 交付（C3）。只读依据：GitHub `#9`/`#29`/`#79` 真实原文与当前项目决策/契约文档，
以及项目源码/清单。**本文件把阻塞转成可审阅决策项，不替用户决定，不猜 ABI，不填数值预算，不发用户问题、不改 Issue。**

非声称：未运行 UE/ROS/native/构建，未读厂商源码，未改资产，未修改任何既有文件（C1/C2 交付文件亦未改动）。

## 一、三分法：必须项 / 已批准最小模型 / 额外扩展能力

### A. #29 原 AC 必须项（来自 #29 票面原文，不可由子票关闭替代）

| # | 原 AC | 分类判定 |
| --- | --- | --- |
| 1 | 冻结一个可核验场景的物理表示、视觉表示、坐标和反馈有效时间 | **必须项**。表示/契约层已由已批准合同覆盖；"视觉表示"的冻结允许是 display-only 清单，**不要求 UE 实机运行** |
| 2 | 在坡面/接触工况中检查高度、接触位置与模型反应，重置后按批准预算可复核 | **必须项**。已批准最小模型可覆盖"接触位置/高度"；"模型反应 + 重置可复核"需要一次真实联合运行与**已批准预算**（预算未定，见第三节 B） |
| 3 | 显示断开及反馈过期按批准契约处理，不能永久复用旧反馈或依赖渲染帧推进物理 | **必须项**。过期/冻结/recover 语义已实现并可离线复核；"显示断开"需要一次真实显示运行 |
| 4 | 保留动态地形/对象变化等额外能力行，不把视觉地面偏移当作碰撞实现 | **必须项（边界项）**。只要求"保留能力行 + 不冒充"，**不要求实现**动态地形/对象 |
| 5 | 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后关闭 | **必须项**。属交付/审查层 |

### B. 已批准最小接触模型（唯一已批准路径，不得扩大解释）

来源：`docs/plan/9-abi-environment-accepted.md` 第一节（绑定 2026-09-07 用户答复"采用此环境与视觉合同"）。

- **权威边界**：WSL 负责静态地形与碰撞，在权威物理步查询几何；UE 从同一带版本/哈希的场景配置生成显示；单位米、公共 ENU、显式原点；UE 换算限于显示边界。
- **加载与 epoch**：静态场景加载失败或哈希不符**启动前拒绝**；当前 epoch 内**不热改**配置。
- **首例几何（测试夹具）**：`z=0` 平面 + 一个轴对齐盒体，盒体中心 `[2,0,0.5]` m、尺寸 `[1,1,1]` m。**明确标注为夹具数值，非厂商场景或实机标定。**
- **接触信封 `wksim.contact.v1`**：`scene_id/scene_hash/epoch/step/sim_time/valid_from_step/valid_until_step/body_id/geometry_id/contact_point_enu_m/normal_enu/penetration_m`；结果只在声明的 authority step 有效；`valid_until_step` 是仿真步边界，**不用墙钟续期**。
- **动态反馈过期**：必需动态反馈缺失或过期时冻结所属联合场景并要求显式恢复；仅显示/图像断流不冻结物理。
- 已批准的最小模型是**纯几何**：只计算并输出几何穿透深度与表面接触点/法线。

### C. 额外扩展能力（#29 原 AC 的**非**前置，属其他票据/门槛）

**关键判定：以下各项均未被 #29 原 AC 要求，不得自动升格为 #29 的前置条件。**

| 扩展能力 | 真实归属 | 与 #29 的关系 |
| --- | --- | --- |
| 接触力/冲量/弹簧刚度/阻尼/摩擦力/wrench | 无任何已批准数值（`9-abi-environment-accepted.md:16` 明文） | **非前置**；#29 只要求不把视觉偏移当碰撞实现 |
| 摩擦、弹性、穿透修正、碰撞求解器参数 | 同上 | **非前置** |
| 坡度动力学、侧碰 | 需先冻结批准输入/预算/失败语义 | **非前置**；属能力行扩展 |
| 动态地形/动态对象 | #29 AC4 只要求"保留能力行" | **非前置**；实现属后续票 |
| 旧/新 DLL ABI、`DllInCtrlExt`/`DllInFromUE`/`VisionSensorReq` 扩展 I/O | #27/#28/#73/#74/#76/#77/#78 | **非前置**；见第三节 A |
| Full / G6 数值、完整动态环境 | #6/G6/Full 门槛 | **非前置** |

**因此：把"力/冲量/侧碰模型"当作 #29 关闭前置，是把扩展能力误升格为原 AC。** #29 关闭需要的是
原 AC 1–5 在已批准最小模型路径上的证据 + 主代理复核；力模型与 ABI 是**平行**的开放项，不是 #29 的准入条件
（除非主会话明确决定提高要求，那属于修改 #29 验收范围，需用户决定）。

## 二、真正尚未批准的项（可审阅决策清单）

### A. ABI（DLL 旧/新）— 状态：NO-GO，无可审阅对象

- 官方 `DllSimCtrlAPI` 文档只给出高层 Python 方法名（`DllInputColls(inCll)` 20 维碰撞输入、`DllGetStep0()`、`Dllstep()`），**没有**权威 C/C++ 原型、调用约定、精确 float 宽度、返回/错误契约、缓冲所有权、生命周期状态机、线程/隔离契约。
- 本地 SDK 复核：`E:\rflysimtools\CopterSim` 递归**未找到**任何 `.h/.hpp/.c/.cpp/.def/.lib`；模型符号只出现在 `DllSimCtrlAPI.py`（SHA `0a2a30e9…`）及其生成 HTML；匹配 `MulticopterNOpx4.dll` SHA `0179c58f…`。
- 已记录的实质缺陷（**禁止批准**）：`DllInputColls` 先声明 `double[20]`（1235–1239 行）后覆盖为 `float[20]`（1292–1296 行）；构造检查 `DllInitPosAngStat` 却访问 `DllInitPosAngState`。
- **决策项 A1**：提供权威头文件/规范 + 一个由该接口构建的最小授权样本 DLL；或**正式放弃**旧/新 DLL 运行路径（保留"自主核心可关闭 DLL 运行"）。
- **决策项 A2**：在 A1 之前是否允许任何 adapter 实施？当前规则：**不允许**（#9 评论明确"不应从推断的 ctypes 形状实施 host 或 adapter"）。
- **决策项 A3**：`DllGetStep0` 导出语义与 `Hexa.xml`/`F450.xml` 元数据（`ClassID=-1` 非资产绑定）是否需独立核验后再评估 —— 属 A1 的从属项。

### B. 数值预算 — 状态：**未批准，且不得由代理代填**

已明示"具体数值预算须在对照运行之前确定"（#9 Working mode），且 `9-abi-environment-accepted.md:16` 记录
"具体坡度、盒尺寸、接触测试和误差预算在切片实现前固定"。**尚未批准**的预算至少包括：

| 预算项 | 现状 | 需要谁决定 |
| --- | --- | --- |
| 接触几何容差（法线单位化容差、边界点零穿透判定） | 实现取精确零穿透/精确边界；**未批准数值** | 用户/主会话（HITL） |
| 接触位置/高度误差预算 | 未批准 | 用户/主会话 |
| 重置后可复核的"批准预算"（AC2 明文引用） | 未批准；probe 仅证明精确重放（`state_trace_equal=true`） | 用户/主会话 |
| 反馈过期/freeze→recover 的可接受步数预算 | 未批准；#81 用的是夹具缺口 `30000 < frame <= 30020` | 用户/主会话 |
| 坡度角/盒尺寸扫描范围 | 未批准（夹具只有 `[2,0,0.5]`/`[1,1,1]`） | 用户/主会话 |
| #6/G6 正式数值预算、#23 R1 `numerical_failed` | **未被本路径替代**，保持原状 | 原门槛 |

### C. 视觉实机证据 — 状态：**缺实现，非缺预算**

- 已存在：display-only 契约与清单 schema（`ContactObserver.get_display_manifest()`，`wksim.display-manifest.v1`），以及 #81 保留的 `display-manifest.json`（display-only authority，明确不能修改 physics）。
- **缺失**：UE5.5 实机显示与权威物理**同置运行**；`60ae5097…`（静态夹具/显示清单）与 `4889e2ea…`（真实模型 probe）两层身份在同一次可复核链路中的落地；UE 显示断开/重连在 #29 场景上的运行；UE/WSL/FC/ROS2/DDS 联合时钟闭环。
- 源码事实（只读核对）：`Simulator/ue55/*.py` 中 `contact`/`terrain`/`scene_hash`/`scene_id` **零出现**；UE C++ 源中无接触信封或显示清单的消费者。
- **决策项 C1**：是否授权一次隔离 UE5.5 资源预约，用于 #29 静态场景的受控显示验证（资源前置见第四节）。
- **决策项 C2**：什么样的证据才算"显示表示已冻结并与权威物理同源"（清单哈希一致 + 逐帧 identity 回读 + 人工截图检查的组合），以及是否接受 display-only 清单作为 AC1 的充分证据。
- **决策项 C3**：#29 场景的显示断开验证，是否接受以现有 `--reconnect-view`/`--reset-scene` 同类驱动扩展实现（需新实现，见第四节）。

## 三、已有批准来源（精确索引）

| 来源 | 内容 | 性质 |
| --- | --- | --- |
| `docs/2026-09-07_environment-contract-accepted.md` + `validation/remaining-gates-20260907/environment-acceptance.json` | 2026-09-07 用户答复"采用此环境与视觉合同"，含提案 SHA256 | **用户批准** |
| `docs/plan/remaining-gates-proposal.md` SHA `abf10c663c235c151207bba142fa4e8798cb02617142465c3b5a46f3d04d7098` | 被批准的提案正文 | **批准依据** |
| `docs/plan/9-abi-environment-accepted.md`（#58 `9-contract` 交付） | 已批准合同 + ABI 证据阻塞 + 五项前置 | **合同记录** |
| `docs/plan/9-abi-environment-evidence.md` SHA `606cb49eb7f226946793df8a6d0e536c867e00d5e9a431c47595a39cb1e91331`、`validation/lunar-57-…/abi-facts.json`、`validation/lunar-58-…/` | ABI 事实与只读命令 | **证据** |
| #9 评论（2026-09-11，官方来源复核） | DLL 半边 **NO-GO**；#73/#74/#76/#77/#78 保持 blocked | **决策结论** |
| `docs/plan/29-contact-observer-contract.md` | 接触观察/冻结恢复契约（纯几何，禁力/冲量/刚度/阻尼/摩擦） | **已实现切片契约** |
| `docs/plan/29-102-scene-binding-contract.md` | planner 场景绑定身份与失败封闭边界 | **已实现切片契约** |
| `docs/plan/29-terrain-evidence-manifest.json` | `status=partial_open`、`acceptance=false`、`blocking_issue=9`、三项 `unproven_boundaries` | **当前状态声明** |

**明确不算批准**：#80/#81 夹具审计通过、`lunar-29-terrain-reset-c8f05c6e` 冷重置精确重放、planner 绑定测试通过——
这些是**证据**，不是接口/预算/视觉运行批准；不得用它们反推 ABI 兼容、数值预算已定或 UE 已实机验证。

## 四、主会话下一步（具体、可执行、不替用户决定）

1. **验收 C1/C2 交付**：`docs/coordination/ds-scene-frontier-20260912.md`、`validation/test_scene_frontier_contract.py`（本队列不再改动这两个文件）。
2. **归档本决策包**：由主会话决定是否将第一节三分法与第二节 A/B/C 决策项并入 #9/#29 决策记录（DS-C 不改 Issue，不发表评论）。
3. **推进 AC1/AC3 的前置是"缺实现"而非"缺预算"**：先补 UE 侧消费者与受控驱动（第四节列出最小清单），再由主代理预约隔离 UE 资源。
4. **AC2 物理推进顺序**：要么按 A1 补齐 ABI 权威对象，要么**正式放弃** DLL 路径并只用 `wk_model_*` seam；两条路都不需要把力/冲量/侧碰升格为 #29 前置。
5. **预算项一律上抛 HITL**：第二节 B 表中任一项在得到用户决定前不得由代理自行填写（代理不代填预算）。
6. **保持 #29 OPEN**，不因 #79/#80/#81 已关闭而关闭父票；**#102 完整 EGO 仍依赖 #29/#33，任何 release 单项不得冒充**。

## 五、C4：一次受控 UE/反馈验证所需的最小条件

**核心结论：对 #29 而言，受控 UE/反馈验证的入口尚不存在。** 现有 UE 入口都是"独立/联合状态显示"验证，
**没有任何一条把 `static-plane-box-v1` / `60ae5097…` 场景身份、`wksim.contact.v1` 接触信封或 terrain 反馈
带进 UE 运行**。因此本节**不给出、也不允许编造**"#29 UE 验证命令"。

### 5.1 已存在的真实入口（可引用其真实参数面，但不等价于 #29 验证）

| 入口 | 真实参数/调用面 | 输入 | 输出 | 能证明 / 不能证明 |
| --- | --- | --- | --- | --- |
| `tools/validate-ue55.ps1` | `-Stack <px4\|arducopter>`（必填，ValidateSet）、`-Stage <E:/ue5.5/build/wksim-native-*>` | UE 工程、已构建模块 DLL、回环 UDP 19060 | `validation/ue55-<stack>-<8hex>/`：`manifest.json`（utc/run_id/pid/engine/project/arguments/evidence/module_sha256）、`ue.log`、`frames/*.png` | 证明真实 UE5.5 D3D12 显示 + Actor 回读 + 视觉断流/陈旧帧处理（其自声明 scope）；**不证明** #29 场景身份、接触信封、terrain 反馈、联合时钟 |
| `tools/validate_ue55.py` | `--stack`、`--evidence`、`--run-id`（均必填）、`--port`（默认 19060）、`--dds-workspace`（默认 `/root/wksim-dds-VxM6Ni`） | 同上 + 私有网络 WSL DDS 飞行真值 | `actor-readback.jsonl`、结果 JSON、`flight.log` | 同上；自声明 "not full-product acceptance" |
| `tools/build-ue55.ps1` | `-Stage`（可选；默认新建 `E:/ue5.5/build/wksim-native-<8hex>`） | `Simulator/ue55/`、P450 资源与清单 | 暂存工程 + 12 项构建输入哈希 | 只证明构建暂存身份 |
| `tools/validate_joint_visual.py` | `--manifest`（必填）、`--output`（必填）、`--reconnect-view`、`--reset-scene` | 候选构建清单 | 联合双机视觉回归证据目录 | 证明联合双机显示、空中重开 UE、冷重置代次隔离；**不是** #29 单场景接触验证 |
| `Simulator/wksim_runtime/contact_observer.py::get_display_manifest()` | 纯 Python，`wksim.display-manifest.v1` | 冻结场景 + epoch | display-only 清单（`scene_id/scene_hash/coordinate_frame/unit/authority`） | 契约侧存在；**无 UE 侧消费者** |
| `validation/lunar-29-live-contact/run.py` + `audit.py` | `python -B validation/lunar-29-live-contact/run.py` / `audit.py`（见其 `commands.txt`） | 只读真值 `validation/arducopter-physics-4yynssup/truth.jsonl` | `records.jsonl`、`events.json`、`display-manifest.json` | 离线证明 stale 冻结（frame 30019 / boundary 29999）与显式恢复（30039）；**未启动 UE/FC/模型**，无新物理 |

### 5.2 资源前置（按真实脚本核对）

- UE 5.5 安装：`E:/ue5.5/files/UE_5.5`（`Engine/Binaries/Win64/UnrealEditor.exe`）。
- 暂存工程：必须是 `E:\ue5.5\build\wksim-native-*` 的**直接子目录、新建或空、且不是重解析点/链接**。
- 已构建模块：`<stage>/Binaries/Win64/UnrealEditor-WksimVisual.dll` 必须存在。
- 渲染：真实 D3D12 窗口（**不使用 NullRHI**）；截图需**人工检查**，不能只看 PNG 存在。
- 网络：Windows 回环 UDP **19060**（单占用，启动器先探测）；WSL 侧私有网络 + DDS 工作区（`--dds-workspace`）。
- 隔离：真实 UE/WSL/SITL 资源须由**主代理预约**，每次运行使用全新证据目录。
- Python：README/脚本使用 `D:/date/miniconda/python.exe`（本机既有解释器）。

### 5.3 明确缺失的实现（#29 受控验证的真实阻塞）

1. **UE 侧消费者缺失**：`Simulator/ue55/*.py` 中 `contact`/`terrain`/`scene_hash`/`scene_id` **零出现**，UE C++ 源无接触信封或显示清单的消费者；`wksim.display-manifest.v1` 目前唯一的读取方是离线审计器 `tools/audit_29_terrain_evidence.py`。
2. **没有绑定 #29 场景身份的运行入口**：没有任何脚本用 `Simulator/wksim_runtime/static-scene-v1.json` / `60ae5097…` 启动 UE 并与权威物理同置运行。
3. **没有 #29 场景的显示断开/重连运行**：`--reconnect-view` 只在联合双机路径存在。
4. **没有 UE/WSL/FC/ROS2/DDS 联合时钟闭环证据**。

**因此：在 5.4 补齐前，任何"#29 UE 验证命令"都是编造，禁止写入文档、脚本或票据。**

### 5.4 最小补齐清单（2–4 个文件；当前**未实现**，名称为建议）

1. `Simulator/ue55/` UE 侧消费者/桥（或在既有 `product_bridge.py`/`state_relay.py` 上扩展），承载 `scene_id/scene_hash/epoch/step` 与 display-only 清单绑定。
2. 受控驱动（建议 `tools/validate_29_scene_binding.py`，或在 `tools/validate_joint_visual.py` 上扩展静态场景路径），完成一次 UE 会话 + 身份同源记录 + freeze/recover 帧证据。
3. 该驱动的纯数据身份回归测试（对应本队列 C2 已建立的失败封闭边界）。
4. 证据目录（命令、源码/配置身份、exit、失败边界），沿用既有 `commands.txt` 约定。

以上 3/4 属于已有约定；1/2 是**新实现**，须由主代理分配写入者与隔离资源后才能宣称可运行。

### 5.5 失败边界（来自真实脚本，非推测）

- 暂存目录守卫：不匹配 `E:\ue5.5\build\wksim-native-*`、非直接子目录、已存在非空或是链接 → 直接 `throw`。
- 模块缺失 → `Build the wksim UE module first`。
- UE 在就绪前退出 → 报错并带实际 exit code。
- 就绪/首帧超时 **120 s**：必须同时满足日志出现 `WKSIM_READY run=<runId>` **且** `frames/` 至少 1 张 PNG。
- 收尾：先 `CloseMainWindow`，10 s 内未退出则终止该 PID（只回收自己创建的进程）。
- `validate_ue55.py`：Actor 误差超容差、外来 Actor 回读、未请求/重复状态变更、非预期飞行证据路径 → `ValueError`；看门狗到期 → `TimeoutError`。
- 端口 19060 被占用 → 回环绑定失败，不允许抢占他人运行。
- #81 离线路径的失败语义固定为：stale 冻结于 frame 30019 / boundary step 29999，恢复于 30039；该路径**不得**被描述成 UE 实机证据。
