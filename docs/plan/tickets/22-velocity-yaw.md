# 22 · 双栈速度与偏航控制能力

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

2026-09-08 语义冻结（按五项批准记录执行）：激活轴为 XYZ_VEL/XYZ_VEL_BODY 惯性速度（机体变体按当前偏航旋转）；**yaw-rate 模式**为双栈公共支持（`yaw_rate_mode=true`，angular.z ENU；PX4 经 TrajectorySetpoint yawspeed，AP 经 DDS `rt/ap/cmd_vel` TwistStamped MAP 帧）；**yaw 角度+速度组合**：PX4 支持（yaw 字段），AP 经 DDS 速度入口仅载偏航速率，受理前以 `arducopter_velocity_requires_yaw_rate_mode` 拒绝且无副作用；XY_VEL_Z_POS*、TRAJECTORY、姿态/推力与全球坐标属 #33/#34/#47，AP 侧仍以 `arducopter_move_mode_not_implemented` 拒绝。控制门槛（运行前冻结）：速度阶跃 (0.8,0.4,0) m/s ENU 逐轴 |Δ|≤0.3 m/s 持续 3s；零保持 |v|≤0.25 m/s 且漂移 ≤1.0 m 持续 4s；偏航速率 0.5 rad/s 积分角 |Δ|≤0.35 rad 持续 4s；拒绝后 2s 无副作用（|v|≤0.25）。

2026-09-08 实施与证据进展：AP 原生速度入口（native_arducopter cmd_vel/TwistStamped）已实现并以新控制候选 FVMjak 通过 81 项候选矩阵（含 2 项新速度测试）；提升飞行 `joint-public-flight-_cs_wxw_`（健康公共位置任务，FVMjak 实飞+独立审计通过）完成准入换绑，joint-profiles 已换钉。**四次正式联合场景速度任务中，双栈速度阶跃/零保持/偏航速率与 AP 无效组合拒绝+无副作用全部以持续真值通过（4/4 相位）**；但全场景干净收尾未达成——两次降落段宿主漂移 rate_unmet（100.02/100.03ms）、一次起飞后原生 freshness 撤销、一次驱动断言缺陷（已修），失败样本全部保留。全场景干净验收与票据关闭待宿主窗口（与 1× 同族宿主层问题），本票继续 OPEN。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

通过同一Prometheus命令在双栈执行速度阶跃、回中保持和偏航/偏航速率控制。

## Acceptance criteria

- [ ] AP所需原生入口或候选变更必须实际构建并匹配消息身份；不能只保留ROS字段。
- [ ] 冻结激活轴、yaw与yaw-rate语义和控制门槛，支持与不支持的组合明确列出。
- [ ] 两栈真实运行速度阶跃、停止保持和偏航工况，并以持续状态/真值验证。
- [ ] 无效组合在受理前拒绝且没有控制副作用，已有位置任务回归通过。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：原生控制。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
