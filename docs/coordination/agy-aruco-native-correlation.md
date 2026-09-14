# #29 场景反馈 / ArUco 目标离线准入检查

2026-09-14。本文件对应只读离线检查器 `tools/inspect_aruco_native_targets.py` 与纯测试 `validation/test_aruco_native_targets.py`。

工作类别是 **new-development 的离线诊断/准入辅助**，不是 UE、native、ROS/DDS、SITL、飞控或飞行验收。

## 1. #9 仍 OPEN 时不能解锁 #29 / #79 / #80 / #81

GitHub `#9`（可选模型插件与场景反馈接口决策）当前为 **OPEN**。本工具把该状态视为硬阻塞：

- 报告里 `issue_9_state` 固定为 `OPEN`。
- `parent_tickets_unlocked` 对 `#29`、`#79`、`#80`、`#81` 一律为 `false`。
- 证据包若自称 `issue_9_state=CLOSED`，记为 `fabricated_issue_9_closure` 并拒绝关联。
- 子票 #79/#80/#81 即使在 GitHub 上已关闭，也不等于父票 #29 的原 AC 已满足；离线工具不得把它们重新标成已解锁。

关闭 #9 之前，本工具不能、也不会把 #29 或其接触切片标成可验收。

## 2. 工具做什么

检查器只读现有场景/证据 JSON，或调用方提供的临时证据包。它只在下列条件**同时**成立时，把视觉 ArUco 目标与物理接触信封标成 `correlated`：

| 条件 | 要求 |
| --- | --- |
| 坐标系 | 场景与视觉记录均为 `coordinate_frame=ENU`，单位 `metre` |
| 反馈有效时间 | 视觉与物理都有 `valid_from_step` / `valid_until_step`；`current_step` 落在区间内；物理 `sim_time_ns = step * 1_000_000` |
| 来源身份 | 视觉与物理信封都有类型合法的 `source_identity`：非空字符串，或非空对象且子字段同样是非空字符串/对象 |
| 过期 / 断流语义 | `stale_feedback` 与 `disconnect` 为非空字符串且不得是静默复用；`render_frame_advances_physics` 必须是布尔 `false` |
| 物理信封 | 完整 `wksim.contact.v1` 字段，与场景 `scene_id` / `scene_hash` / `epoch` 一致 |
| 非视觉偏移 | 不得用 ArUco `position_world_ue_m`、地面视觉偏移或 `collision_from=visual` 冒充碰撞 |
| 类型门 | 见下一小节；空串、空对象、`bool` 冒充、NaN/Infinity、长度错误均拒绝 |

缺任一项即 `rejected`，不关联。过期记 `stale_feedback`，超前记 `future_feedback`，混写 `60ae5097…` / `4889e2ea…` / `40ee9281…` 记身份冲突。

### 类型门

关联前先做字段类型检查，不启动 UE/物理：

- `source_identity`：拒绝 `""`、`{}`、`True`/`False`、列表，以及对象里的空子字段。
- `step` / `current_step` / `valid_from_step` / `valid_until_step` / `sim_time_ns` / 若出现的 `valid_for_steps`：必须是非负 `int`，**显式排除** Python `bool`（因此 `step=0` 且 `sim_time_ns=False` 不能靠 `False==0` 过关）。合法的整数 `0` 仍可用。
- `contact_point_enu_m`、`normal_enu` 以及出现的 `position_*` / `origin_enu_m`：长度恰好为 3 的有限数值序列；拒绝字符串、错误长度、元素为 `bool`、`NaN`、`Infinity`。
- `penetration_m` 及同类标量：有限数值，排除 `bool`。
- `scene_id` / `scene_hash` / `epoch` / `body_id` / `geometry_id`：非空字符串，不用真值判断冒充。

独立复核的三个反例（物理 `source_identity=""`、`step=0`+`sim_time_ns=False`、`contact_point_enu_m="not-a-vector"`）现为正式 unittest。

工具**不**伪造已批准接触预算：信封或包内出现 `force` / `impulse` / `stiffness` / `damping` / `friction` / `wrench` 等字段即拒绝，输出也不补这些量。

## 3. 直接依赖的现有路径

| 路径 | 用途 |
| --- | --- |
| `Simulator/wksim_runtime/static-scene-v1.json` | 冻结静态夹具 `static-plane-box-v1` / `60ae5097…`，ENU / 米 |
| `docs/plan/29-terrain-evidence-manifest.json` | #29 证据边界；`acceptance=false`，`blocking_issue=9` |
| `validation/lunar-29-live-contact/display-manifest.json` | 若存在则核对夹具身份与 display-only 声明；单独清单不是视觉/物理对 |

当前检出若无 `validation/lunar-29-static-contact/` 或 `validation/lunar-29-live-contact/`，检查器记 `retained_live_evidence_unavailable`，不编造这些目录的内容或审计通过。清单存在只证明身份可核对，不证明 UE 已运行。

默认命令（无证据包）只核对这些已提交路径，结论仍是拒绝关联、不解锁父票。

## 4. 工具已证

纯 Python 测试覆盖的是**离线准入边界**，不是现场物理：

- 证据齐全时可以关联视觉记录与物理信封，但仍因 #9 OPEN 保持四张票未解锁。
- 缺坐标系、有效时间、来源身份、过期/断流语义时拒绝。
- 空串/空对象/`bool` 来源身份、`bool` 冒充时间字段、非向量/NaN/Infinity/长度错误的接触与位置序列均拒绝。
- 仅视觉偏移、把 ArUco UE 位姿当作接触点、渲染帧推进物理、静默复用旧反馈时拒绝。
- 未批准力学字段不会被写成“已批准接触预算”。
- 三层场景身份不可混写；单独的静态场景 JSON 或证据清单不足以构成视觉/物理对。
- 本检出缺失的 lunar-29 实况目录不会被补造。
- 输出独占 `'x'` 写入；模块不导入 ROS / DDS / 运行时物理求解。

`correlated` 只表示这包离线字段够用来对照，不是 #29 AC 通过。

## 5. 仍需真实 UE / 物理场景的部分

下列内容本工具**不能**证明，也不得用离线关联代替：

- UE5.5 实机显示与权威物理同置；真实显示断开/重连。
- 坡度、侧碰、接触力/冲量/刚度/阻尼/摩擦、动态地形或动态对象。这些预算尚未批准，检查器不会发明。
- 飞控 / SITL / ROS2 / DDS 联合时钟闭环。
- 把 `60ae5097…`（静态夹具/显示清单）与 `4889e2ea…`（生成模型 probe）当成同一次 UE 运行。
- 在 #9 仍 OPEN 时关闭或解锁 #29 / #79 / #80 / #81。

#29 原 AC 仍全部未勾选。本切片不启动 UE / native / model / MATLAB / ROS / DDS / SITL / FC / build / flight，也不改 GitHub。

## 6. 命令

```text
python -B -m unittest validation.test_aruco_native_targets
python -B tools/inspect_aruco_native_targets.py --retained-paths
python -B tools/inspect_aruco_native_targets.py --evidence <PACK.json> --output <OUT.json>
```

`--output` 以独占 `'x'` 创建文件；已存在则拒绝覆盖。
