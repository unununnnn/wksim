# G4 地形接口（#29）最短可执行闭环梳理

检查点：`validation/coordination/omp-g4-terrain-readiness-20260913-01/`，HEAD `e05993f`。
只读核对 + 纯 Python 探针；未修改任何既有文件，未 git add/commit/push，未启动/终止任何进程，未加载 .so/.dll。

## 目标定位（从证据，不假设）

- G4 = "Full 工具与互操作"（`docs/plan/goal-objective.md:29`、`full-remaining-ledger.md:21`）。
- G4 的地形接口部分 = issue **#29 坡面与障碍场景的物理反馈**。
- gh 只读核对（2026-09-14）：**#29 OPEN**，5 条原 AC 全未勾选，Blocked-by #17/#23/#9 仍生效；**#9 OPEN**（ABI NO-GO）；#17/#23/#79/#80/#81 CLOSED；#33/#39/#102/#26 OPEN。子票关闭不满足父票 AC。

## 接口现状

| 层 | 文件/符号 | 状态 |
| --- | --- | --- |
| 权威几何 | `Simulator/wksim_core/static_contact.py` `StaticScene.query/require_fresh/support_height_enu_m`，`wksim.contact.v1` | 已实现且有独立审计 |
| 场景配置 | `Simulator/wksim_runtime/static-scene-v1.json`（`static-plane-box-v1`，sha `60ae5097…`） | 冻结，重算哈希一致 |
| 运行时观察 | `contact_observer.py` `ContactObserver`（freeze/recover/display manifest） | 已实现 |
| 地形接缝 | `terrain_feedback.py` `TerrainFeedback.query_terrain`（Vehicle60→ENU→Terrain15D） | 已实现，wired |
| 联合接线 | `joint.py:33,52,185-188`；`joint_runtime.py:636-638,722` | 已接线（opt-in） |
| planner 绑定 | `planner_scene_binding.py` `EGO_SINGLE_BOX_BINDING`（5 个冻结哈希，`forces/impulses/terrain_response=false`，`visual_mirror not_bound`） | 已实现，纯离线 |
| planner profile | `wksim_planning/scene_profile.py`（`ego-single-box-v1`） | 已实现 |
| UE 侧消费者 | `Simulator/ue55/*.py` 中 contact/terrain/scene_hash/scene_id **零出现** | **缺失（P0）** |
| FC 闭环 | `tools/probe_joint_terrain_feedback.py` `DeterministicNativeIOStub`（:409） | **仍是 stub（P0）** |

## 本轮验证（主会话已实际执行）

- 探针：`python -B validation/coordination/omp-g4-terrain-readiness-20260913-01/probe.py` → **21/21 pass**（接口形状 5、配置/消息身份 5、失败关闭 11；明细见 `probe-output.json`）。
- 纯测试：160 项通过（62 + 98），1 项 Windows 符号链接权限 skip（WSL 侧覆盖）。
- 夹具审计复跑：`lunar-29-static-contact` 85 断言 pass；`lunar-29-live-contact` 30895 断言/3253 行 pass。

## 已满足 / 未满足

**已满足（证据边界内）**：AC1 表示合同层（冻结物理表示+display-only 清单+单步时效）；AC2 部分（静态几何、垂直 terrain seam、生成模型 elevated 冷重置精确重放）；AC3 合同层（stale/future/foreign-epoch/scene-hash 冻结+显式恢复）；AC4 边界层（WSL 权威、无视觉偏移冒充碰撞）；AC5 交付层。三层场景身份（`60ae5097…`/`4889e2ea…`/`40ee9281…`）互斥有回归。

**未满足**：真实 UE5.5 同置显示运行与显示断开/重连（AC1/AC3）；坡度动力学、接触力/冲量/刚度/阻尼/摩擦、侧碰、动态对象（AC2/AC4）；FC 闭环（probe 为确定性 stub）；AC2 "批准预算" 未批准；父依赖 #9 未解除。#29 必须保持 OPEN。

## 主会话可立即执行的最小闭环（纯离线，今日可跑）

`scene_profile → planner_scene_binding.query → contact_observer.observe_step → terrain_feedback.query_terrain → JointPhysics tick 接线` 已闭环可验证：

```
python -B validation/coordination/omp-g4-terrain-readiness-20260913-01/probe.py
python -B -m unittest validation.test_contact_observer validation.test_terrain_feedback validation.test_static_contact validation.test_scene_frontier_contract
python -B -m unittest validation.test_joint_terrain_feedback validation.test_probe_joint_terrain_feedback validation.test_planner_scene_binding validation.test_scene_profile validation.test_audit_29_terrain_evidence validation.test_trajectory_session
python -B validation/lunar-29-static-contact/audit.py
python -B validation/lunar-29-live-contact/audit.py
```

此闭环只证明接口形状/身份钉扎/失败关闭；**不是** UE/FC 闭环证据，不得当作 #29 父票验收。

## 阻塞（P0/P1/P2）

- **P0-1** UE 侧消费者与 #29 场景驱动缺失：`Simulator/ue55/*.py` 无消费者；无绑定 `60ae5097…` 的运行入口；无 #29 场景断开/重连运行。解除：主会话分配写入者 + 预约隔离 UE5.5 资源；决策 C1/C2/C3 待批准（`ds-interface-decision-packet-20260912.md` §5.4）。
- **P0-2** FC 闭环为 stub：`tools/probe_joint_terrain_feedback.py:409` `DeterministicNativeIOStub`。解除：主会话预约隔离 SITL/FC/ROS2/DDS。
- **P0-3** 父依赖 #9 OPEN（ABI NO-GO）。解除：权威 ABI 材料或正式放弃 DLL 路径（用户决定）；此前只用已审查 `wk_model_*` seam。
- **P1-1** 数值预算未批准（几何容差/高度误差/freeze→recover 步数/坡度扫描），一律上抛 HITL，代理不得代填。
- **P1-2** 两层身份未在同一次可复核链路落地（禁止自动合并 `60ae5097…` 与 `4889e2ea…`），依赖 P0-1。
- **P2-1** 动态地形/对象/坡度变化/侧碰仅为能力行，需先冻结批准输入/预算/失败语义。
- **P2-2** 1 项 planner 绑定符号链接测试在 Windows 无权限 skip；WSL 验收检出覆盖，无需改码。

## 下一实现切片（不与 G3/#102/#26/core-audit 当前改动冲突）

**显示场景绑定的权威侧契约模块 + 纯测试**（决策包 §5.4 第 1/3/4 项的离线部分）：

- 新文件：`Simulator/wksim_runtime/display_scene_binding.py`（`wksim.display-manifest.v1` 绑定校验 + freeze/recover 帧证据 schema，不控 UE 进程）、`validation/test_display_scene_binding.py`、`docs/plan/29-display-binding-contract.md`。
- 只新建文件；禁触：`ego_scene_admission.py`、`planner_transport_pump.py`、`audit_26_closure_readiness.py`、`audit_core_no_vendor_dll.py` 及其测试与 `docs/plan/102-*`（当前他方 M 状态）；`joint.py/worker.py/model.py`（契约明令禁改）；DS-C 已交付两文件；UE 资产与既有证据目录。
- 前置：主会话确认写入者；真实 UE 运行与驱动（§5.4 第 2 项）仍门控于 C1/C2/C3 与隔离资源预约；预算留 HITL。
- 冲突核验：与 HEAD `e05993f` `git status` 中全部他方修改文件零重叠。

## 非声称

未运行 UE/SITL/FC/ROS/DDS/MATLAB/native 构建/厂商模型；未关闭或编辑任何 issue（#29 保持 OPEN）；旧飞行 PASS 不转移；mixed/Full/G6 状态不变。
