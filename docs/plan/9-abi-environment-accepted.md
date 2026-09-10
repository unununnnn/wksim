# #9 ABI 与环境反馈：已批准与证据阻塞记录

2026-09-10。本文是 GitHub #58（稳定键 `9-contract`）的交付，记录 #26–#29 范围内的**已批准合同**与**证据阻塞项**。部分批准不宣称任何 ABI 或完整动态环境已完成。#9 保持开放。

## 一、已批准：环境与视觉反馈合同（绑定 2026-09-07 用户决定）

用户在 2026-09-07 对当前任务明确回答**“采用此环境与视觉合同”**，批准依据为 `docs/plan/remaining-gates-proposal.md` 的环境/视觉方案；原问题、答复和提案 SHA256 保存于 `validation/remaining-gates-20260907/environment-acceptance.json`，正文见 `docs/2026-09-07_environment-contract-accepted.md`。绑定的确切条目：

1. **权威边界**：首例由 WSL 负责静态地形与碰撞，在权威物理步查询几何；UE 从同一带版本/哈希的场景配置生成显示。单位米，公共 ENU 和原点明确，UE 换算限于显示边界。
2. **加载与 epoch**：静态场景加载失败或哈希不符启动前拒绝；当前 epoch 不热改配置。
3. **RGB**：按已应用的权威状态异步采集，携带运行代次、步号、模型时间、载具/传感器/帧身份、实际采集位姿、尺寸/编码、内参和安装外参；墙钟采集/传输时间单独记录。丢帧可见，旧 epoch 拒绝，重连只交付当前帧；显示或图像断流不决定物理节拍。
4. **动态反馈过期**：未来必需动态环境反馈缺失或过期时冻结所属联合场景，并要求显式恢复；仅显示/图像断流不因该合同冻结物理；真实主机资源不足仍遵守 #8 的监督预算。
5. **首例几何（测试夹具）**：`z=0` 平面与一个轴对齐盒体，盒体中心 `[2,0,0.5]` m、尺寸 `[1,1,1]` m（夹具数值，非厂商场景或实机标定）。静态几何记录 `valid_from_step`/`valid_until_step` 及 epoch。
6. **接触信封**：独立 `wksim.contact.v1`：`scene_id/scene_hash/epoch/step/sim_time/valid_from_step/valid_until_step/body_id/geometry_id/contact_point_enu_m/normal_enu/penetration_m`。结果只在声明的 authority step 有效；`valid_until_step` 是仿真步边界，不用墙钟续期。依据：已批准的 1 ms authority tick / 4 ms 输入屏障与“过期反馈不可静默复用”原则。

**未批准范围**：摩擦、弹性、穿透修正、接触力模型、碰撞求解器参数与动态对象没有任何已批准数值；平面/盒体只验证几何绑定、单位、原点和接触查询接缝，不能报告为环境反馈通过。具体坡度、盒尺寸、接触测试和误差预算在切片实现前固定。

## 二、证据阻塞：DLL ABI（旧/新均未批准，无可审阅对象）

依据 #57 交付的 `docs/plan/9-abi-environment-evidence.md`（SHA256 `606cb49eb7f226946793df8a6d0e536c867e00d5e9a431c47595a39cb1e91331`）及 `validation/lunar-57-6d85dab1b5ff4b84a3a5e58b1fc467a1/abi-facts.json`：

- `DllSimCtrlAPI.py`（SHA256 `0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420`）存在真实冲突：`DllInputColls` 先声明 `double[20]`（1235–1239 行）后覆盖为 `float[20]`（1292–1296 行）；构造检查 `DllInitPosAngStat` 却访问 `DllInitPosAngState`。**两项均禁止批准**。
- `DllOutCopterData`、`DlloutVehileInfo60d`、`Dllstep`、`DllReInitModel`、`DllDestroyModel` 的 Python-side 形状不足以证明导出端完整 C ABI、错误码与所有权；`DllGetStep0` 导出语义未独立核验。
- supplied sample 只证明 legacy Python 调用意图；不证明导出符号、许可、同一模型版本或公开分发权。
- `Hexa.xml`/`F450.xml` 的 ModelInfo/HoverInfo/FrameInfo 元数据可读，但与 wksim 生成候选（质量 1.515）不同源；`ClassID=-1` 不是资产绑定。
- `VisionSensorReq` 的 `16H28f` 只是字段线索；缺 epoch、权威 step、源/接收时间与新鲜度语义。

**进入 ABI 实施票的前置（缺一不可，否则保持 `needs-triage`）**：

1. 每个样本独立 manifest：导出名、调用约定、参数指针/数组长度、`float`/`double`/整数类型、返回类型及错误码；
2. 输入/输出字段的单位、坐标、时间、所有权和写入时机；
3. 加载→初始化→输入→step→读取→重置新 epoch→终止/卸载的状态图；
4. DLL 崩溃、step 错误、短输出、重复重置和线程/UDP 残留的隔离结果；
5. 文件 SHA、来源/许可和允许的本机使用范围；可读头文件或包装源及合法使用依据。

在 manifest 未齐前，wksim 只保证自主核心能关闭 DLL 运行；任何未知 legacy/new 导出均拒绝，不用 wrapper 可导入性代替互操作证明。

## 三、对 #26–#29 的约束结论

| 父票 | 本记录结论 |
| --- | --- |
| #26 生成模型构建导入 | Exp1 材料已固定哈希（本机 local-only）；Exp2 材料缺失为显式阻塞；DLL 路径未批准 |
| #27 旧 ABI 生命周期 | **阻塞**：满足第二节 5 项前置后方可派票 |
| #28 新 ABI 与扩展输出 | **阻塞**：同上；`DllInCtrlExt`/`DllInFromUE`/`VisionSensorReq` 仅线索 |
| #29 坡面/障碍物理反馈 | 第一节合同为唯一已批准路径；#29 仍保留 #23 数值前置，首例切片按 OPS-07 合同派票执行 |

## 四、不变量与失败边界

- #6/G6 正式数值预算未被本记录替代；R1 保持 `numerical_failed`；#20/#33 RateUnmet 不变。
- 本记录不加载/执行/修改厂商 DLL 或安装，不分发厂商源码/二进制，不推断一揽子授权。
- 环境与视觉批准不覆盖未知 DLL ABI、未核实样本对应关系或硬件条件（#56 另行清点）。

## 来源身份

- `docs/2026-09-07_environment-contract-accepted.md`（用户批准正文）
- `validation/remaining-gates-20260907/environment-acceptance.json`（答复与提案 SHA256）
- `docs/plan/remaining-gates-proposal.md` SHA256 `abf10c663c235c151207bba142fa4e8798cb02617142465c3b5a46f3d04d7098`
- `docs/plan/9-abi-environment-evidence.md` SHA256 `606cb49eb7f226946793df8a6d0e536c867e00d5e9a431c47595a39cb1e91331`
- `validation/lunar-57-6d85dab1b5ff4b84a3a5e58b1fc467a1/abi-facts.json`
- 本 slice 证据：`validation/lunar-58-fbf56d9d50e1df62/`（只读命令与事实 JSON）
