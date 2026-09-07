# 联合场景显示接缝 v3

对应已批准实施票 #21。本接缝只分发已提交的真实物理状态，不接收飞行或物理步进命令。既有单机 v2 与历史诊断 v1 保留原行为。环境碰撞与相机数据不由本接缝实现，也不越过 #9。

由正式联合 manager 为一次运行创建随机 `instance_id`（32 位小写 hex），各次冷重置采用严格递增 `generation`（从 1 开始）与新的 `epoch`。UE 启动参数明确选择 joint、run_id 和 instance_id；不通过首次无条件收到的包选择运行。

UDP/Unix datagram 中的 JSON 包最多 8192 字节，顶层恰含以下 19 个字段，额外字段拒绝：

|字段|契约|
|---|---|
|version / kind|整数 3 / `joint_state`|
|run_id / instance_id|已选择运行名称 / 已选择 manager 身份|
|epoch / generation|32 位小写 hex / 正整数，冷重置递增|
|sequence|本 epoch 内严格递增，0..2^53−1|
|step / sim_time_ns|已提交公共步号 / 精确 step×1000000，整数且不超过 2^53−1|
|phase|`running`、`paused`、`faulted` 或 `stopped`|
|source_wall_time_s|发送墙钟秒；仅用于过期检查，不作为物理时间|
|position_frame / position_unit / quaternion_order / body_frame|`NED` / `m` / `WXYZ` / `FRD`|
|rotor_unit / rotor_order / configuration|`rpm` / `[FR,RL,FL,RR]` / `quad-X`|
|vehicles|1 或 2 个对象；正常生产包包含两机，新 generation 首包必须包含两机|

每个 vehicles 对象恰含 `vehicle_id`（1/AP 或 2/PX4）、`stack`（`arducopter` 或 `px4`）、`position_ned_m[3]`、`quaternion_wxyz[4]`、`rotor_rpm[4]`、`model_time_s`。数值有限、四元数平方模误差不超过 1e−5、坐标绝对值不超过 1e6m、RPM 0..100000。原模型时间必须与公共 step/1000 在现有模型数值表示精度 1e−8s 内一致；该时间编码核对不作为 G6 动力学预算。物理 state 数组中的模型时间保留，不事后改写。

接收年龄沿用既有产品显示接缝 −0.25..0.75s。WSL relay 用自身墙钟验证原 source_wall_time_s；Windows bridge 按同 WSL 源龄加完整 monotonic 往返计算保守年龄，追加 `display_clock=windows_utc_bound`、`display_wall_time_s`、`transport_age_bound_s`，送往 UE 的对象因此恰为 22 个字段。UE 只用 Windows 显示时刻检查年龄，不将跨系统 UTC 差当作物理误差；原 source_wall_time_s、模型时间、epoch/step 保留不变。

相同 epoch 的 step 可以相等（暂停/故障状态更新），不能倒退；sequence 严格增加。generation 相同但 epoch 不同、generation 倒退或 instance 不符的包拒绝。有效新 generation 包原子清除旧代次各机显示记录；不能由旧包恢复旧 Actor。一个包缺少某机时，只更新实际包含者；缺失者超过 0.75s 标为陈旧。这用于独立显示丢包验证，正常 publisher 不故意丢弃某机。

UE 创建两个身份独立的 P450 Actor，沿用现有 mesh/material，不生成或修改资产，不对物理位置加展示偏移。当前两机共享原点与公共任务目标可能靠近或重合，必须如实显示；HUD 标签与观察选择用于区分，不能伪造分离出生点。旋翼显示相位按收到的权威步增量和实际 RPM 推进，暂停不按渲染墙钟继续积分。无碰撞/动力学权威迁移到 UE。

当前联合显示资源档采用 15 FPS，状态 writer 最多 20 包/墙钟秒。这个档位只控制显示工作量，不改变 1ms 模型步、4ms 原生输入屏障、物理倍率或 100ms 迟到预算；不是 RGB 传感器帧率承诺。单机显示原 30 FPS 档保留。

原生界面支持 1/2 或 Tab 切换跟随观察目标，并显示两机的名称、状态、步号与位置。返回的 `joint_actor` ACK 包含 version=3、run_id/instance_id/epoch/generation/sequence/step/sim_time_ns、selected_vehicle_id，以及本次已应用各机的 `vehicle_id`、`ue_position_cm`、`ue_quaternion_xyzw`、`rotor_rpm`、实际组件 `rotor_yaw_deg`。另返回两机 `observed_vehicles`（vehicle_id/step/stale/visible）和实际 `camera_position_cm`；相机跟随在收到包后的该帧稍后更新，需下一包验证观察目标位置。ACK 仅用于只读证据，任何缺失、超时或 UE 退出都不能影响物理调度。

主线负责 manager 身份、配置、状态 writer/relay 与真实测试。UE 文件由独占代理实现此已批准显示切片；共享真实 FC/UE 测试按主线预约串行进行。

CLI/SDK 可用 `View.select_vehicle(1|2)` 切换相同的观察目标。它只向当前 UE 回环端口发送恰含 version=3、kind=joint_view_select、run_id、instance_id、epoch、generation、request_sequence、vehicle_id 的 8 字段请求；UE 要求当前身份、代次及严格递增的请求号。响应只将 kind 改为 joint_view_selected，客户端不重试，后续状态 ACK 再读回实际选择和相机。该网络入口不进入飞控或物理进程。原生键盘自动化服务当前退出，键盘验收保留，不能以 SDK 的成功冒称实际键盘已测。
