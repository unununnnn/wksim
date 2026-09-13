# #9 模型 ABI 与环境反馈证据合同（未批准）

2026-09-09。本文是 #57 `9-evidence` 的证据交付，不是 #9 决策关闭，也不是旧/新 DLL 已兼容或环境反馈已实现的声明。所有未知布局、返回值、生命周期和许可状态继续 fail closed。

## 证据来源

| 材料 | 实际路径 | SHA256 | 结论用途 |
| --- | --- | --- | --- |
| SDK DLL 控制包装 | `E:/rflysimtools/RflySimAPIs/RflySimSDK/ctrl/DllSimCtrlAPI.py` | `0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420` | Python ctypes 声明、调用顺序和冲突证据 |
| SDK 视觉请求 API | `E:/rflysimtools/RflySimAPIs/RflySimSDK/vision/VisionCaptureApi.py` | `f69a3c50e0d335136b3d83070bf380e7579bd25dfd80ae291a2548d5b79dd7ee` | `VisionSensorReq` 字段/长度线索 |
| Hexa XML 元数据 | `E:/rflysimtools/CopterSim/external/XML/Hexa.xml` | `e5a7ddb311313d7cc0d0dda57783389ce7673f0fdaa9b1f6bc61230090a23e13` | 六旋翼 Model/Hover/Frame 元数据对照 |
| F450 XML 元数据 | `E:/rflysimtools/CopterSim/external/XML/F450.xml` | `1215bbac83631c1a89a15c3b609cf88365a72fb832d9ee76eef7ca70b59e9489` | 四旋翼元数据差异对照 |
| 合法样例入口 | `E:/rflysimtools/RflySimAPIs/4.RflySimModel/0.ApiExps/12.DllModelImport/9.ModelLoadCopterSim30100Python/DllSimCtrlAPITest.py` | `3510c3a62611720d95ea65b08587713998b24aa607339a0dfa7413b69833b392` | supplied sample 的加载/调用顺序，不等于许可或 ABI 证明 |
| 当前缺口提案 | `docs/plan/remaining-gates-proposal.md` | `abf10c663c235c151207bba142fa4e8798cb02617142465c3b5a46f3d04d7098` | 既有候选选择与未知边界 |

上表中的样例哈希连续值为 `3510c3a62611720d95ea65b08587713998b24aa607339a0dfa7413b69833b392`；路径/哈希均来自本机实际读取。厂商目录未被修改，DLL 未被加载或执行。

## 已证实的 legacy 包装事实

`DllSimCtrlAPI.py` 的 `ModelLoad.__init__`（约 1176 行）接受 `dll_name, CopterID, ClassID, MapName, ip, LocX, LocY, Yaw, UdpMode, useGPS, GpsOrin`，通过 `ctypes.CDLL` 加载 DLL，配置部分符号，然后调用 `CreateVehicle`。`CreateVehicle`（约 1342 行）执行地形输入、可选 GPS 原点、位置/姿态初始化、模型重初始化、一次 `Dllstep`，之后读取输出并通知三维显示。

实际观察到的 Python-side 声明如下。它们是包装器的调用意图，不是已由公开 C/C++ 头文件确认的 ABI：

| 符号 | 包装器传入/读取形状 | 返回/生命周期观察 | 当前判定 |
| --- | --- | --- | --- |
| `DllInputSILs` | `int[8]` + `float[20]` | 输入 SIL 状态；返回类型未固定 | wrapper 线索 |
| `DllInputColls` | 文档和后段方法使用 `float[20]`；构造配置 1235–1239 行先写过 `double[20]`，1292–1296 行又覆盖为 `float[20]` | 返回类型未固定 | **冲突，禁止批准** |
| `DllInitGpsPos` | `double[3]` | 设置 GPS 原点；返回类型未固定 | wrapper 线索 |
| `DllInitPosAngState` | `double[3]` 位置 + `double[3]` 角度 | 方法约 1884 行直接调用同名导出；返回类型未固定 | 参数形状可读，导出返回值未知 |
| `DllInitPosAngStat` | 构造配置 1248、1255 行检查该名字，却访问 `self.dll.DllInitPosAngState` | 名称检查与访问不一致 | **命名冲突，禁止批准** |
| `DllTerrainIn15d` | `double[15]` | 地形输入；返回类型未固定 | wrapper 线索 |
| `DllInputDoubCtrls` / `DllinSIL28d` | `double[28]` | 外部控制输入；返回类型未固定 | wrapper 线索 |
| `DllInCtrlExt` | `double[140]` | 故障/扩展控制输入；返回类型未固定 | wrapper 线索 |
| `DllInFromUE` | `double[32]` | UE 到 DLL 扩展输入；返回类型未固定 | wrapper 线索 |
| `DllGetStep0` | 无参数 | wrapper 设置 `c_double` 返回；无导出时回退 `0.001` | 返回类型有 Python 声明，导出语义仍未独立核验 |
| `DllReInitModel` / `Dllstep` | 无参数 | wrapper 设置 `c_int` 返回；调用处忽略返回值 | 状态码语义和失败行为未知 |
| `DllOutCopterData` | wrapper 声明 `double[32]` 输出指针、`None` 返回；方法约 2021 行按 32 项读取 | 构造处声明和后续调用一致性不足 | **需头文件/样本核对** |
| `DlloutVehileInfo60d` | `double[60]` + `int` 长度，`None` 返回 | 方法约 2003 行分配 60 项并传长度 | wrapper 线索，符号拼写需冻结 |
| `DllDestroyModel` | 无参数 | `None` 返回；关闭路径调用 | 是否幂等、是否释放线程/网络资源未知 |

实际代码还存在 `DllOutCopterData` 构造阶段设置 `argtypes=[double[32]]`、后续调用 `self.DllOutCopterData()` 由 Python 方法内部重新分配数组的双层封装；未有独立 C 头文件证明导出端调用约定。不能仅凭 `hasattr`、符号名或 ctypes 成功设置批准加载。

## Legacy 与新 ABI 的边界

当前可追溯的 legacy 样例只显示：`DllSimCtrlAPI.DllSimCtrlAPI(CopterID=1)` → `InitTrueDataLoop()` → `RflySimCP.getPosNED/getVelNED` → `sendInDoubCtrls()`。样例中碰撞、扩展控制、UE 输入、故障和初始化操作多为注释调用；它证明了样例意图，不证明每个导出符号存在、长度正确或模型返回值有效。

当前 wksim 自主核心使用自有、独立的 `wk_model_create` / `wk_model_step` / `wk_model_destroy` 风格接口和显式 120 项输出；这是自主核心边界，不是对 `DllSimCtrlAPI` legacy ABI 的隐式兼容声明。旧 ABI、任何所谓 new ABI、ROS/DDS CDR 类型和模型物理语义都必须分别有 manifest、头文件/包装源、实际样本和生命周期审计。

未来允许进入实现票的 ABI manifest 至少应固定：

1. 每个函数的导出名、调用约定、参数指针/数组长度、`float`/`double`/整数类型、返回类型及错误码；
2. 输入/输出字段的单位、坐标、时间、所有权和写入时机；
3. 加载→初始化→输入→step→读取→重置新 epoch→终止/卸载的状态图；
4. DLL 崩溃、step 错误、短输出、重复重置和线程/UDP 残留的隔离结果；
5. 文件 SHA、来源/许可和允许的本机使用范围。

在 manifest 未齐全前，wksim 只保证自主核心能关闭 DLL 运行；任何未知 legacy/new 导出均拒绝，不用一个 wrapper 的可导入性代替互操作证明。

## XML 与参数对应关系

实际 `Hexa.xml` 的 `ModelInfo` 读到质量 `1.8`、重力 `9.8`、惯量对角 `0.0211/0.0219/0.0366`、半径 `0.225`、推力系数 `1.105e-05`、力矩系数 `1.779e-07`、稳态转速 `1148`、电机时间 `0.05`；`FrameInfo` 为 6 旋翼/6 机臂。实际 `F450.xml` 质量为 `1.4`、`FrameInfo` 为 4 旋翼/4 机臂。两份 XML 的 XML 元数据与本机 wksim 生成 Hex 候选质量 `1.515`、自有 source-template 参数不能直接等同。

`ClassID=-1` 在 XML 与 SDK 中表示让 DLL/模型侧决定三维样式的线索；它不能证明 UE 资产路径、`Unique3DClassID`、旋翼层级或模型参数已绑定。`ModelInfo`、`HoverInfo`、`FrameInfo` 的字段语义和默认值必须作为独立元数据合同，不从相邻文件名推导 DLL/ZIP 同源。

## 视觉与环境反馈候选合同

### 静态几何候选（未批准）

为 #9 的第一个可验证接缝，候选使用一份带 `scene_id`、canonical 配置 SHA 和 epoch 的静态场景：

- 公共单位为米，公共坐标为 ENU，原点和朝向显式记录；
- 一个 `z=0` 平面和一个轴对齐盒体，盒体中心 `[2,0,0.5]` m、尺寸 `[1,1,1]` m；这些是测试夹具数值，不是厂商场景或实机标定；
- WSL 权威物理按每个 authority step 查询同一几何，UE 只从同一 hash 配置生成显示几何；显示帧不驱动物理；
- 静态几何记录 `valid_from_step` / `valid_until_step` 及 epoch；epoch 内不可热改，配置/hash 不一致在启动前拒绝。

该平面/盒体只用于验证几何绑定、单位、原点和接触查询接缝。没有已批准的摩擦、弹性、穿透修正、接触力、碰撞求解器或动态对象参数，不能把它报告为环境反馈通过。

### 接触与有效期候选（未批准）

动态接触输出建议使用独立 `wksim.contact.v1` 信封：`scene_id/scene_hash/epoch/step/sim_time/valid_from_step/valid_until_step/body_id/geometry_id/contact_point_enu_m/normal_enu/penetration_m`。候选规则是：结果只在声明的 authority step 有效；必需反馈超过一个 authority step 未更新则冻结所属联合场景并要求显式恢复；纯 UE 显示或 RGB 断流不冻结物理。`valid_until_step` 是仿真步边界，不使用墙钟续期。

上述“一步有效”选择以已批准的 1ms authority tick / 4ms 输入屏障和“过期反馈不可静默复用”的工程原则为依据，但本候选仍需 #9 决策确认；它不是当前代码已实现的场景/碰撞合同，也不是动态环境测试预算。

## 视觉请求的已知缺口

`VisionCaptureApi.py` 的 `VisionSensorReq` 注释给出 `16H28f`：16 个 `uint16` 与 28 个 `float`，并列出 checksum、`SeqID`、`TypeID`、目标载具、宽高、FOV、安装位置/角度和保留参数。它可作为字段线索；SDK 注释和包装没有提供 wksim 需要的 epoch、权威采样 step、source/receive 时间或新鲜度合同。wksim RGB Consumer 已经采用自己的 `wksim.rgb.v2`/`wksim.rgb-ready.v2` 信封，这不是对 SDK 原始结构逐位兼容的声明。

## 结论、失败边界与后续准入

- 已证实：SDK 包装器存在真实 float/double 与符号名称冲突；XML 能提供可读的模型/悬停/机架元数据；样例展示了 legacy Python 调用顺序；本机自主核心有独立 API。
- 未证实：任一 legacy/new DLL 的完整 C ABI、所有导出存在性、返回值、内存/线程所有权、重置/卸载安全性、XML 与 DLL/SLX/ZIP 的同源关系、厂商资源的公开分发权。
- 本票没有加载或执行厂商 DLL，没有修改厂商安装，也没有批准 #9 的环境反馈策略或 #27/#28 的 ABI 实现。
- 下一张 ABI 实施票必须先收到每个样本独立 manifest、可读头/包装源、合法使用依据和一个可隔离的最小生命周期样本；缺任一项则保持 `needs-triage`。
- 静态平面/盒体候选必须在实现前获得具体决策，随后单独验证几何、接触、过期、动态变化和停止/重连；它不能被 RGB、Hex 静态模型或旧 XML 读取证据替代。
