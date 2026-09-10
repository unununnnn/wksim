# #104 · ArUco 相机目标到公共速度意图：运行合同

状态：2026-09-10。**接缝纯逻辑已实现并通过离线合同测试；真实飞行未验证（UNVERIFIED）。**

主会话后续复核：修正了原 `TargetIntent` 的反馈方向，采用“观测机体系相对位置 − 期望位置”；此方向与 Prometheus `aruco_tracking.cpp:175–180` 一致，并由静止目标相对运动的独立三轴回归验证误差减小。目标丢失/坏帧不再擦除当前绑定的去重高水位；同 epoch 可显式换新相机 stream，冷重置可保留原 stream，退役流不能复活；新绑定前捕获的目标拒绝。当前 36 项 TargetIntent/接缝检查通过，不替代真实飞行。
本合同记录实际接口、所有者、运行前必须预冻结的预算和后续运行命令所需内容。
不把候选通过当生产提升；#104 完成条件要求两栈同场真实证据，当前不具备。

## 实际接口链（已存在的部件 + 本切片新增接缝）

| 段 | 部件 | 输入 → 输出 | 状态 |
| --- | --- | --- | --- |
| 图像采集 | `Simulator/ue55/rgb.py` `Reader.poll()`（`rgb.py:123`） | UDP ready 通知 → `wksim.rgb.v2` 元数据 + PNG 路径 | 既有，未改 |
| 图像消费 | `Simulator/wksim_perception/aruco.py` `Consumer.consume/current`（`aruco.py:141,105`） | Reader 帧 → `wksim.aruco-target.v1`（含 run/epoch/instance/generation/stream/vehicle/sensor/step/valid_until_step、机体系 FLU、世界诊断、重投影） | 既有，未改 |
| 目标→意图 | `Simulator/wksim_perception/target_intent.py` `TargetIntent.update` | 新鲜目标 → `wksim.target-intent.v1`（XYZ_VEL_BODY 或 HOLD） | 复用并修正反馈方向及去重水位 |
| **接缝（本切片新增）** | `Simulator/wksim_runtime/aruco_tracking_input.py` `ArucoTrackingSeam.update` | 目标 + 权威步 → `wksim.aruco-tracking-input.v1`（含 intent、`command` 与 `hold_action`） | 新增，离线测试通过 |
| 公共速度入口 | 运行时任务 `Task.send`（`Simulator/wksim_runtime/task.py:320`）发布公共 `UAVCommand`（legacy_v1）或 `CommandRequest`（session_v1，`task.py:93-101`） | `command_fields` → 公共命令字段 | 既有，本切片未接入 |

接缝的公共命令映射只有一组字段：`agent_cmd=MOVE`、`move_mode=XYZ_VEL_BODY`、
`velocity_ref`、`yaw_rate_mode=True`、`yaw_rate_ref=0.0`（对应
`ros2/src/prometheus_msgs/msg/UAVCommand.msg:12,29` 的 MOVE=4、XYZ_VEL_BODY=4）。
Consumer 的诊断世界位置/速度、重投影残差从不进入命令字段。

HOLD 或任何非 XYZ_VEL_BODY 意图的 `command` 为 `None`，但**这不等价于停止旧速度**：
控制处理器每周期重新解算最近一次接受的 MOVE 命令（`command.py` `step`，新命令由
`accept` 替换），不发布不会停车。接缝因此在每条 HOLD 记录附带显式
`hold_action`：`{required:true, public_command:"CURRENT_POS_HOVER"}`，要求运行时任务经
`Task.send` 发布公共 CURRENT_POS_HOVER（`UAVCommand.msg:10` agent_cmd=2，以当前位置悬停
替换持续速度设定值）或走其撤权路径。只交映射/动作需求，不发 ROS、不改控制器。

## 权威门（同场闭环的成立条件）

接缝只接受 `wksim.aruco-joint-authority.v1` 权威记录，字段对应：

- `kind=joint_scene`、`run_id`/`epoch`/`instance_id`/`generation` —— 来自联合运行时
  状态行（`Simulator/wksim_runtime/joint_runtime.py:135-139` 的 status 行与
  `epoch_run` 结果 `:86-89`）。
- `stream_id` —— 权威 View 的 RGB 流身份（`Simulator/wksim_console/visual.py:134`；
  View 要求 `joint_instance` 才允许配置 RGB，`visual.py:110`）。
- `run_id` —— 项目规则 `Simulator/wksim_core/state_stream.py:15`
  （`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`），不是 hex32；真实 #103 运行
  `aruco-scene-267899ace7` 即此形状。`epoch`/`instance_id`/`stream_id` 仍按
  `Consumer.bind`/`Reader.set_epoch` 的 hex32 严格校验。
- `camera` —— 相机所属 joint 载具（1..2）与传感器 ID，须与目标帧的
  vehicle_id/sensor_id 一致。
- `vehicles` —— 必须同时含 `px4` 与 `arducopter` 两条目，且共享同一
  run_id/epoch。**单栈状态、缺一条目、epoch 不一致一律拒绝**；
  UE 侧 `WksimVisualGameMode::TickRgb` 本就要求两个当前 JointVehicles
  （见 `docs/plan/40-aruco-live-scene-contract.md:79`），本门与该原生事实一致。

拒绝语义：权威步回退 → `ValueError`（重放帧不是新鲜权威）；外来
instance/generation/vehicle/sensor/stream 目标 → seam HOLD 且不消费目标步；
过期/未来/重复目标 → TargetIntent HOLD；HOLD 永远 `command=None` 且附 `hold_action`。
绑定转移沿用 `Consumer.bind`（`aruco.py:84-103`）/`Reader.set_epoch`（`rgb.py:68-83`）：
新 epoch 要求代次严格升高，可保留仍活动的 stream；同 epoch 相机重连可显式换新 stream，但不单独升代；同身份重绑保留
保留 TargetIntent 去重历史；退役 epoch/stream 不能复活；所有校验先于状态改写，
失败不部分改写；`rebind` 的 authority_step 参数必须等于记录内值，不允许矛盾。
`_step` 字符串与整数路径都受 0..9007199254 上界约束。


## 所有者

| 文件/区域 | 所有者 | 本切片动作 |
| --- | --- | --- |
| `Simulator/wksim_runtime/aruco_tracking_input.py` | 本切片（新建） | 已实现 |
| `validation/test_aruco_tracking_input.py` | 本切片（新建） | 已实现，与 TargetIntent 合计36项通过 |
| `Simulator/wksim_perception/target_intent.py` | #53 交付 | 只读复用 |
| `Simulator/wksim_perception/aruco.py`、`Simulator/ue55/rgb.py` | 既有 Consumer/Reader | 只读复用 |
| 运行时任务/配置/联合接入（见下） | 主会话 | 未改，差异在下节 |

## 主会话待合入的接入差异（本切片未改任何既有文件）

1. `Simulator/wksim_runtime/config.py` 严格白名单：新增显式任务 profile
   （建议键 `aruco-tracking-v1`），携带冻结合同身份；无默认飞行参数。
2. 联合任务工厂（`Simulator/wksim_runtime/joint_task.py` 的 `task_class`）与 `joint_runtime.py` 的任务设置/动作门，配合 `joint_config.py` 的任务类型及实际预检能力：
   新任务类在 joint 双栈运行内创建 Consumer + 本接缝，`command_fields` 非 None 时经
   `Task.send` 发布公共 UAVCommand/CommandRequest，`command_id` 逐次递增
   （`UAVCommand.msg:47-48`）。
3. 权威记录装配：从 joint status 行 + View RGB 绑定构造
   `wksim.aruco-joint-authority.v1`；UE View 在 Windows、运行时在 WSL，
   帧传输沿用既有 UDP 通知 + 共享路径（#103 已验证的 Reader 路径），不新增通道。
4. 场景生成侧沿用 #103 的 `tools/validate_aruco_scene.py`/`audit_aruco_scene.py`
   与 UE 候选；本切片未动其源码与证据目录。

## 运行前必须预冻结的预算（当前未冻结，不预设值）

- `TargetIntentConfig`：`desired_body_flu_m`、`gain_per_s`、`max_speed_mps`（接缝强制显式，无默认）。
- Consumer 门槛：目标有效期步数、最大距离、世界速度/突跳门槛、重投影 RMS 上限
  （#103 场景合同 `:33-44` 的候选值仅作输入，不是飞行批准值）。
- 每栈：出现/移动/遮挡/恢复四阶段的最少样本数、速度误差门槛只在连续新鲜运动帧比较
  （Consumer 目标过期后诊断速度为 null 是正确行为，不作为失败）。
- 同场证据绑定：图像、目标、CDR 控制记录、物理真值必须共享同一 run/epoch/step；
  回放只能做接口测试（#40 AC4）。

## 后续运行命令所需内容（未交付，飞行部分未验证）

#104 完成条件要求两栈同场真实证据；以下入口尚不存在，本文不宣称其可运行：

1. 联合运行入口加 `--task aruco-tracking-v1` 与冻结 profile 路径/SHA；
2. 独立原始审计器：从原始 PNG/元数据、目标记录、控制 CDR、物理 1ms 真值重建
   出现/移动/遮挡/恢复，拒绝重放帧、跨 epoch 拼接与诊断速度冒充命令；
3. 每栈一次真实运行的 Luna 子票（#104 操作步骤 3）。

当前可复制命令（纯逻辑，不启动 SITL/UE/ROS）：

```powershell
python -B -m unittest validation.test_aruco_tracking_input -v
```
