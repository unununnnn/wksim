# 27 · Prometheus NE控制器闭环

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户选择NE控制器，经相同任务和姿态出口验证其实际响应。

## Acceptance criteria

- [ ] 迁移实际NE方法及必要状态，保留来源与初始化/复位差异。
- [ ] 配置、事件和证据标识实际控制器，拒绝不满足标定/周期条件的运行。
- [ ] 双栈完成预先定义的定点、轨迹和扰动工况。
- [ ] 退出、失联和新代次不复用旧算法状态，其他控制器回归通过。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [Prometheus PID控制器选择与闭环](https://github.com/unununnnn/wksim/issues/35)

## Parallel boundary

本票建议归属：控制算法。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
