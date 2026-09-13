# #29 display-scene binding contract

2026-09-14。本文记录 G4/#29 的零冲突离线切片：权威侧 `wksim.display-manifest.v1` 绑定校验，以及 contact/frame 消费与 freeze/recover 帧证据 schema。本切片不控制 UE 进程，不关闭 #29，也不把离线通过写成父票 AC。

## 工作类别与核验

- 工作类别：new-development
- 实际 cwd / 分支 / HEAD：`C:/Users/PC/Documents/odid编译/wksim`，`main`，开工时 `676d9e8542b2571a413929f274e4c3d2f08e8f34`
- 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：退出码 0
- 已读：根 `AGENTS.md`、`CONTEXT-MAP.md`、`wksim/CONTEXT.md`、ADR-0002/0004/0008、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/short-cycle-goal.md`、`docs/coordination/module-delivery-policy-20260912.md`、`validation/coordination/omp-g4-terrain-readiness-20260913-01/review.md`/`review.json`
- module / interface：`Simulator/wksim_runtime/display_scene_binding.py` 消费 `wksim.display-manifest.v1`、`wksim.contact.v1`、`wksim.display-frame.v1`、`wksim.display-frame-evidence.v1`
- 独占新建文件：本模块、`validation/test_display_scene_binding.py`、本文
- 未改：`ego_scene_admission.py`、`planner_transport_pump.py`、`joint.py`/`worker.py`/`model.py`、UE 资产、既有证据目录、#26/#102 他方文件

## 复用的身份

显示消费只接受冻结夹具，三层身份保持互斥：

| 层 | scene_id | scene_hash | 本切片 |
| --- | --- | --- | --- |
| 显示夹具 / contact observer | `static-plane-box-v1` | `60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514` | 唯一可消费的 display 身份 |
| planner ego / scene_profile | `ego-single-box-v1` | `40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba` | 拒绝作为 display；`visual_mirror.binding_status=not_bound` |
| 生成模型 probe | `static-plane-box-v1-real-tick0` | `4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300` | 拒绝作为 display |

`terrain_feedback` 清单 schema 仍为 `wksim.terrain-feedback-manifest.v1`，scene 身份必须与显示夹具相同，栈体仍为 `arducopter→uav1`、`px4→uav2`。本模块不查询地形、不改 Joint 接线。

显示清单接受两种已存在的 `wksim.display-manifest.v1` 形状，且必须与绑定场景逐字节一致：

1. `ContactObserver.get_display_manifest()`：`origin_enu_m` / `plane` / `box`
2. `#81` 保留文件 `validation/lunar-29-live-contact/display-manifest.json`：`display_geometries` + display-only `authority`

坐标系固定 ENU、单位 metre。权威句为：physics 在 WSL，清单只用于显示，不能修改物理。

## contact / frame 消费

- 接触信封必须是完整 `wksim.contact.v1`，字段集合与 `CONTACT_FIELDS` 一致；`step`/`valid_from_step`/`valid_until_step` 等于 frame，`sim_time_ns = frame * 1_000_000`。
- `no_contact` 与 `frozen` 的 envelope 必须为 null，不得伪造接触对象。
- 陈旧、超前、异 epoch、哈希错位与非法几何沿用 `ContactObserver` 冻结语义；未冻结时不能声称 frozen frame。frozen frame 必须等于 observer 记录的权威 freeze step，恢复请求必须使用绑定 epoch。
- 禁止消费 force / impulse / stiffness / damping / friction / wrench 字段。
- freeze/recover 帧证据 schema 为 `wksim.display-frame-evidence.v1`：证据 epoch 必须与 validator 绑定 epoch 相同，恰好一次 freeze 后一次 recover，recover.frame > freeze.frame。`#81` 离线钉为 freeze frame `30019` / boundary `29999` / recover `30039`，并由测试与已提交 `events.json` / `run-config.json` 交叉核验。该钉是记录式证据，不是 UE 断开/重连运行。
- `ue_session`、`ue_disconnect_reconnect`、`acceptance` 必须为 false；`display_modifies_physics` 必须为 false。

## 验证

```text
python -B -m unittest validation.test_display_scene_binding
```

纯 Python、确定性、不启动 UE/ROS/FC/native/MATLAB/build。通过只证明本切片的身份绑定与 fail-closed 消费，不转移旧飞行 PASS。

## 未满足门槛

#29 保持 OPEN。本切片不满足：

- AC1 真实 UE5.5 与权威物理同置显示运行
- AC2 坡度动力学、接触力/冲量/刚度/阻尼/摩擦、侧碰、动态对象、已批准数值预算、FC 闭环
- AC3 真实 UE 显示断开/重连，以及 UE/WSL/FC/ROS2/DDS 联合时钟闭环
- 父依赖 #9 仍 OPEN（ABI NO-GO）
- planner `visual_mirror` 仍为 `not_bound`；决策包 §5.4 第 1/2 项的 UE 消费者与受控驱动仍未实现
