# 30 · 真实相机驱动ArUco目标跟踪

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者在真实相机场景中指定一个标记目标，运行Prometheus感知与跟踪闭环。

## Acceptance criteria

- [ ] 先冻结标记场景、标定、外参、有效期和遮挡策略；不把推荐ArUco默认扩大为所有感知demo。
- [ ] 图像采集、检测、机体系目标与双栈飞行关联同一运行证据。
- [ ] 目标出现、移动、遮挡和恢复分别验证距离/速度/突跳门槛。
- [ ] 回放可做接口测试，但只有真实传感器到实际飞行闭环通过才关闭本票。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [带时间与标定的真实RGB相机](https://github.com/unununnnn/wksim/issues/30)
- [双栈速度与偏航控制能力](https://github.com/unununnnn/wksim/issues/32)
- [双飞控 SITL 首期验收与迁移顺序决策](https://github.com/unununnnn/wksim/issues/6)

## Parallel boundary

本票建议归属：感知。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
