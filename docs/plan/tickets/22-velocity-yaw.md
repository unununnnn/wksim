# 22 · 双栈速度与偏航控制能力

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

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
