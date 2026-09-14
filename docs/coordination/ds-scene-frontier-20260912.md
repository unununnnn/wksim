# DS-C 场景反馈前沿：#29 原 AC 剩余缺口与下一独立切片

2026-09-12。滚动队列 DS-C（场景反馈前置负责人）单文件交付。本切片独立于审计组与倍率组。

## 一、审查基线与非声称

- 只读核对：GitHub `#29`/`#79`/`#80`/`#81` 与父依赖 `#17`/`#23`/`#9` 的真实票面状态；
  `docs/plan/29-terrain-closure-report.md`、`docs/plan/29-contact-observer-contract.md`、
  `docs/plan/29-102-scene-binding-contract.md`、`docs/plan/29-terrain-evidence-manifest.json`、
  `tools/probe_joint_terrain_feedback.py`，以及相关源码/测试的公开接口与覆盖清单。
- **未**启动 UE/ROS/SITL/模型/构建，**未**读厂商源码，**未**改资产，**未**改 Issue，
  **未**修改共享 runtime/消息/physics 或任何既有验证器。本文件是唯一新增文件之一（另一个见第五节）。

## 二、票面真实状态（2026-09-12 实测）

| 票 | 标题 | 状态 | 关闭时间 |
| --- | --- | --- | --- |
| #29 | 坡面与障碍场景的物理反馈 | **OPEN**（原 AC 5 条全部未勾选） | — |
| #79 | [Astra] 实现已批准的一种坡面/盒体接触模型 | CLOSED | 2026-09-10 |
| #80 | [Luna] 执行已冻结坡面/盒体接触夹具 | CLOSED | 2026-09-10 |
| #81 | [Luna] 执行一次可视场景与物理反馈验证 | CLOSED | 2026-09-10 |
| #17 | 单载具产品状态流接入 UE5.5 | CLOSED | 2026-09-05 |
| #23 | 四旋翼固定工况数值对照 | CLOSED | 2026-09-09（R1 `numerical_failed` 边界保留） |
| #9 | 可选模型插件与场景反馈接口决策 | **OPEN**（ABI NO-GO） | — |

**结论一：子票三张全部关闭，父票 #29 一条未勾。** #29 票面明确写着"关闭本父票仍需原依赖和原AC全部满足"，
子票关闭不构成父票 AC 满足。父依赖 #17/#23/#9 仍按原票面生效：#17/#23 已关闭但**各自的关闭边界不等于
#29 的联合地形验收**；#9 仍 OPEN 且为 `29-terrain-evidence-manifest.json` 声明的 `blocking_issue`。

## 三、#29 原 AC 逐条剩余缺口

| # | 原 AC | 当前状态 | 还缺什么（可核对） |
| --- | --- | --- | --- |
| 1 | 冻结一个可核验场景的物理表示、视觉表示、坐标和反馈有效时间 | 表示/证据层成立 | 两个场景身份层（`60ae5097…` 静态夹具+显示清单、`4889e2ea…` 真实生成模型 probe）不可混写；**没有 UE5.5 实际运行**，冻结的视觉表示仍只是 display-only 清单 |
| 2 | 坡面/接触工况检查高度、接触位置与模型反应，重置后按批准预算可复核 | 部分成立 | 已证明的是平面/盒体静态几何、垂直 terrain-height seam、elevated 冷重置精确重放；**缺坡度动力学、接触力/冲量/刚度/阻尼/摩擦、侧碰、动态对象**；probe 的 native I/O 是确定性 ACK + 4 ms barrier stub，非 FC 闭环 |
| 3 | 显示断开及反馈过期按批准契约处理，不能永久复用旧反馈或依赖渲染帧推进物理 | 部分成立 | 静态契约层已有 freeze/recover 与单步时效证据；**缺真实 UE 显示断开/重连运行**，以及 UE/WSL/FC/ROS2/DDS 联合时钟闭环证据 |
| 4 | 保留动态地形/对象变化等额外能力行，不把视觉地面偏移当作碰撞实现 | 边界层成立 | 能力行与权威边界保留（WSL 权威、display-only）；动态地形/对象、坡度变化、侧向接触本身仍 BLOCKED |
| 5 | 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后关闭 | 交付层成立 | 证据/身份/失败边界齐全（含首个 probe 失败目录）；此项 PASS 只覆盖交付与边界记录，**不覆盖第 1–4 项的运行/物理范围** |

清单自证一致：`29-terrain-evidence-manifest.json` 仍为 `status=partial_open`、`acceptance=false`、
`blocking_issue=9`，并声明三项 `unproven_boundaries`（真实 UE 物理同置、FC 闭环、坡度/接触力动力学）。
本切片未修改该清单，故以上状态为当前有效状态。

## 四、本切片发现的真实覆盖缺口（已由本队列当轮补齐，见第五节）

核对既有测试覆盖清单后发现一个**纯数据/身份/时效边界确实无任何测试覆盖**：

1. **第三层场景身份未被约束。** `Simulator/wksim_runtime/planner_scene_binding.py` 只把
   `static-plane-box-v1` / `60ae5097…` 作为 `LEGACY_SCENE_ID`/`LEGACY_SCENE_HASH` 显式拒绝；
   而 `29-102-scene-binding-contract.md:60-62` 明文声称真实生成模型 probe 身份
   （`static-plane-box-v1-real-tick0` / `4889e2ea…`）"也不是 UE 显示身份，且不在此处被替换"。
   全仓 `validation/*.py` 中 **`4889e2ea` 与 `40ee9281` 零出现**；既有 `test_planner_scene_binding.py`
   只覆盖 legacy 夹具身份，`test_audit_29_terrain_evidence.py` 只覆盖清单内两层身份互换/合并。
   即：契约已声明、真实接口已实现、但**无回归守住 probe 身份不得被当作 planner/显示身份**。
2. **`TerrainFeedback` 注入观察器的身份/时次一致性未覆盖。** `TerrainFeedback(epoch, observers=…)`
   是公开参数，既有测试中 `observers=` 零出现。实测：注入 epoch 与运行 epoch 不符的观察器时，
   查询在真实接缝处 `foreign_epoch` 冻结（fail-closed，不静默复用旧反馈），但该行为此前无回归。

两者均可用真实接口的纯输入离线回归，不新增运行 API、不改共享代码。本队列已按 C2 落地为
`validation/test_scene_frontier_contract.py`（新增文件，不覆盖任何既有验证器）。

## 五、交付结论：能马上独立做的一个切片 + 其余准确外部阻塞

**可马上独立完成的切片（本轮已做，2 个文件，离线纯 Python，无 UE/SITL/FC/ROS/构建）：**

- `docs/coordination/ds-scene-frontier-20260912.md`（本文件，场景前沿核对记录）
- `validation/test_scene_frontier_contract.py`（三层身份互斥 + probe 身份 fail-closed + 注入观察器时次 fail-closed 回归）

该切片是当前 #29 剩余工作中**唯一不需要外部资源**的部分；已过夹具（`lunar-29-static-contact`、
`lunar-29-live-contact`、`lunar-29-terrain-reset-c8f05c6e`）未重做，其审计结果保持不变。

**其余原 AC 的准确外部阻塞（不能由离线静态证据补足）：**

| 阻塞项 | 性质 | 解除条件 |
| --- | --- | --- |
| AC1/AC3 真实 UE5.5 显示运行与显示断开/重连 | 需隔离 UE 资源 | 主代理预约 UE5.5 运行，并把 UE 显示清单与权威物理场景身份在**同一次可复核链路**中落地（禁止自动合并 `60ae5097…` 与 `4889e2ea…`） |
| AC2 接触力/冲量/刚度/阻尼/摩擦、坡度、侧碰、动态对象 | 需先有批准的接触/求解契约 | #9 解除（当前 ABI NO-GO），并冻结批准的输入/预算/失败语义；不得以视觉偏移或未批准力学字段绕过 |
| AC2/AC3 FC 闭环（当前为确定性 stub） | 需真实 FC+SITL 联调 | 主代理预约隔离 SITL/FC/ROS2/DDS 资源 |
| 父依赖 #9 | 外部依赖仍 OPEN | 官方 DLL/插件 ABI 证据（调用约定/类型/错误/所有权/生命周期/线程隔离）；在此之前继续使用已审查的 `wk_model_*` seam |

**关于 #102：** #102 完整 EGO 仍依赖 #29/#33，本切片及任何 release 单项**不得冒充** #102 完整 EGO，
也不得冒充 #29 父票通过。本轮不关闭、不改写任何 Issue。

## 六、非声称

本文件与配套测试都是离线文档/纯 Python 数据切片，未运行真实模型、构建、UE、SITL、FC、ROS 或 MATLAB；
未提交、未推送；未修改源代码、测试、协调 JSON、清单或既有保留证据。
